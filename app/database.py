import json
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

from app.config import Settings
from app.state import ConversationMemory


class DatabaseManager:
    """数据库访问层：业务数据查询 + 会话记忆持久化。"""

    def __init__(self, settings: Settings) -> None:
        """初始化数据库引擎。"""
        self.settings = settings
        self.engine = create_engine(settings.database_url, future=True)

    def bootstrap(self) -> None:
        """启动时初始化会话相关表结构。"""
        self._create_memory_tables()

    def _create_memory_tables(self) -> None:
        """创建 agent 会话与消息表（若不存在）。"""
        with self.engine.begin() as conn:
            for statement in filter(None, self._memory_schema_sql().split(";")):
                sql = statement.strip()
                if sql:
                    conn.execute(text(sql))

    @staticmethod
    def _memory_schema_sql() -> str:
        """返回会话记忆表的建表 SQL。"""
        return """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_id VARCHAR(255) PRIMARY KEY,
            state_json LONGTEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agent_messages (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            session_id VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL,
            content LONGTEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_agent_messages_session_id (session_id)
        );
        """

    def query_rows(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行查询并返回多行字典结果。"""
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return [dict(row._mapping) for row in result]

    def query_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """执行查询并返回首行；无结果时返回 `None`。"""
        rows = self.query_rows(sql, params=params)
        return rows[0] if rows else None

    def get_catalog(self) -> Dict[str, List[str]]:
        """读取用户名、地址、商品名目录，供实体识别使用。"""
        user_names = self.query_rows("SELECT user_name FROM User_info ORDER BY user_name;")
        addresses = self.query_rows("SELECT DISTINCT address FROM User_info ORDER BY address;")
        product_rows = self.query_rows(
            """
            SELECT browse_item AS item_name FROM User_logs
            UNION
            SELECT buy_item AS item_name FROM User_Buy
            ORDER BY item_name;
            """
        )
        return {
            "user_names": [row["user_name"] for row in user_names],
            "addresses": [row["address"] for row in addresses],
            "product_names": [row["item_name"] for row in product_rows],
        }

    def get_schema_overview(self) -> Dict[str, List[Dict[str, Any]]]:
        """返回核心业务表结构，供规划器做 schema-aware 规划。"""
        overview: Dict[str, List[Dict[str, Any]]] = {}
        for table_name in ("User_info", "User_logs", "User_Buy"):
            overview[table_name] = self.query_rows(f"SHOW COLUMNS FROM {table_name}")
        return overview

    def load_memory(self, session_id: str) -> ConversationMemory:
        """加载指定会话记忆；不存在则返回空记忆。"""
        row = self.query_one(
            "SELECT state_json FROM agent_sessions WHERE session_id = :session_id",
            {"session_id": session_id},
        )
        if not row:
            return ConversationMemory(session_id=session_id)
        payload = json.loads(row["state_json"])
        validator = getattr(ConversationMemory, "model_validate", None)
        if validator:
            return validator(payload)
        return ConversationMemory.parse_obj(payload)

    def save_memory(self, memory: ConversationMemory) -> None:
        """保存会话记忆（不存在则插入，存在则更新）。"""
        dumper = getattr(memory, "model_dump_json", None)
        if dumper:
            payload = dumper()
        else:
            payload = memory.json(ensure_ascii=False)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO agent_sessions(session_id, state_json, updated_at)
                    VALUES (:session_id, :state_json, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE state_json = :state_json, updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {"session_id": memory.session_id, "state_json": payload},
            )

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """向消息表追加一条会话消息。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO agent_messages(session_id, role, content)
                    VALUES (:session_id, :role, :content)
                    """
                ),
                {"session_id": session_id, "role": role, "content": content},
            )

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按时间倒序返回会话消息历史。"""
        return self.query_rows(
            """
            SELECT role, content, created_at
            FROM agent_messages
            WHERE session_id = :session_id
            ORDER BY id DESC
            LIMIT :limit
            """,
            {"session_id": session_id, "limit": limit},
        )
