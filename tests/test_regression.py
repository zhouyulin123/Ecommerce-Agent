import copy
import unittest
from unittest.mock import patch

from app.infra.config import Settings
from app.runtime.state import ConversationMemory
from app.runtime.workflow import MarketingWorkflow
from app.utils.location import normalize_location_text


USERS = [
    {"user_id": 1, "user_name": "褚亦", "phone": "13800000001", "address": "上海市浦东新区"},
    {"user_id": 2, "user_name": "李然", "phone": "13800000002", "address": "北京市朝阳区"},
    {"user_id": 3, "user_name": "王敏", "phone": "13800000003", "address": "上海市徐汇区"},
]

VIEWS = [
    {"user_name": "褚亦", "item_name": "羊毛衫", "shop_name": "秋冬服饰店", "enter_time": "2026-03-01 10:00:00", "exit_time": "2026-03-01 10:05:00"},
    {"user_name": "褚亦", "item_name": "羊毛衫", "shop_name": "秋冬服饰店", "enter_time": "2026-03-02 11:00:00", "exit_time": "2026-03-02 11:04:00"},
    {"user_name": "褚亦", "item_name": "高领毛衣", "shop_name": "秋冬服饰店", "enter_time": "2026-03-03 09:30:00", "exit_time": "2026-03-03 09:35:00"},
    {"user_name": "王敏", "item_name": "羊毛衫", "shop_name": "暖冬旗舰店", "enter_time": "2026-03-02 14:00:00", "exit_time": "2026-03-02 14:07:00"},
    {"user_name": "李然", "item_name": "羽绒服", "shop_name": "北方服饰店", "enter_time": "2026-03-04 16:00:00", "exit_time": "2026-03-04 16:05:00"},
]

BUYS = [
    {"user_name": "褚亦", "item_name": "围巾", "shop_name": "秋冬服饰店", "enter_time": "2026-03-04 12:00:00", "exit_time": "2026-03-04 12:02:00", "quantity": 1, "order_amount": 99.0},
    {"user_name": "王敏", "item_name": "羊毛衫", "shop_name": "暖冬旗舰店", "enter_time": "2026-03-05 13:00:00", "exit_time": "2026-03-05 13:02:00", "quantity": 1, "order_amount": 199.0},
]


class FakeDatabaseManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._memories = {}
        self._messages = {}

    def bootstrap(self) -> None:
        return None

    def load_memory(self, session_id: str) -> ConversationMemory:
        return copy.deepcopy(self._memories.get(session_id, ConversationMemory(session_id=session_id)))

    def save_memory(self, memory: ConversationMemory) -> None:
        self._memories[memory.session_id] = copy.deepcopy(memory)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self._messages.setdefault(session_id, []).append({"role": role, "content": content, "created_at": "2026-03-15 10:00:00"})

    def get_history(self, session_id: str, limit: int = 20):
        history = list(self._messages.get(session_id, []))
        return list(reversed(history[-limit:]))

    def get_catalog(self):
        product_names = sorted({row["item_name"] for row in VIEWS} | {row["item_name"] for row in BUYS})
        return {
            "user_names": [row["user_name"] for row in USERS],
            "addresses": [row["address"] for row in USERS],
            "product_names": product_names,
        }

    def get_schema_overview(self):
        return {
            "User_info": [{"Field": "user_id"}, {"Field": "user_name"}, {"Field": "address"}],
            "User_logs": [{"Field": "browse_item"}, {"Field": "enter_time"}],
            "User_Buy": [{"Field": "buy_item"}, {"Field": "order_amount"}],
        }

    def query_one(self, sql: str, params=None):
        params = params or {}
        if "FROM User_info" in sql:
            for row in USERS:
                if row["user_name"] == params.get("user_name"):
                    return dict(row)
        return None

    def query_rows(self, sql: str, params=None):
        params = params or {}
        normalized_sql = " ".join(sql.split()).lower()
        if "from user_logs" in normalized_sql and "browse_item as item_name" in normalized_sql:
            return self._query_recent_views(params)
        if "from user_buy" in normalized_sql and "buy_item as item_name" in normalized_sql:
            return self._query_recent_buys(params)
        if "group by user_id, user_name, address" in normalized_sql or "from ( select ui.user_id" in normalized_sql:
            return self._query_audience_rows(params)
        return []

    @staticmethod
    def _matches_product(item_name: str, product_name: str) -> bool:
        return not product_name or item_name == product_name

    def _query_recent_views(self, params):
        rows = [
            {
                "item_name": row["item_name"],
                "shop_name": row["shop_name"],
                "enter_time": row["enter_time"],
                "exit_time": row["exit_time"],
            }
            for row in VIEWS
            if row["user_name"] == params.get("user_name") and self._matches_product(row["item_name"], params.get("product_name"))
        ]
        return rows[:10]

    def _query_recent_buys(self, params):
        rows = [
            {
                "item_name": row["item_name"],
                "shop_name": row["shop_name"],
                "enter_time": row["enter_time"],
                "exit_time": row["exit_time"],
                "quantity": row["quantity"],
                "order_amount": row["order_amount"],
            }
            for row in BUYS
            if row["user_name"] == params.get("user_name") and self._matches_product(row["item_name"], params.get("product_name"))
        ]
        return rows[:10]

    def _query_audience_rows(self, params):
        product_name = params.get("product_name")
        user_name = params.get("user_name")
        raw_location = (params.get("location_scope_raw") or "").strip("%")
        normalized_location = (params.get("location_scope_normalized") or "").strip("%")
        limit = int(params.get("limit") or 20)
        rows = []
        for user in USERS:
            if user_name and user["user_name"] != user_name:
                continue
            if raw_location and raw_location not in user["address"] and normalized_location not in normalize_location_text(user["address"]):
                continue
            user_views = [row for row in VIEWS if row["user_name"] == user["user_name"] and self._matches_product(row["item_name"], product_name)]
            user_buys = [row for row in BUYS if row["user_name"] == user["user_name"] and self._matches_product(row["item_name"], product_name)]
            if not user_views and not user_buys:
                continue
            rows.append(
                {
                    "user_id": user["user_id"],
                    "user_name": user["user_name"],
                    "address": user["address"],
                    "view_count": len(user_views),
                    "last_view_time": max((row["enter_time"] for row in user_views), default=None),
                    "buy_count": len(user_buys),
                    "last_buy_time": max((row["enter_time"] for row in user_buys), default=None),
                    "total_quantity": sum(int(row["quantity"]) for row in user_buys),
                    "total_amount": float(sum(float(row["order_amount"]) for row in user_buys)),
                }
            )
        rows.sort(key=lambda item: (-item["buy_count"], -item["view_count"], item["user_name"]))
        return rows[:limit]

    def list_sessions(self, limit: int = 20):
        sessions = []
        for session_id, memory in self._memories.items():
            history = self._messages.get(session_id, [])
            sessions.append(
                {
                    "session_id": session_id,
                    "updated_at": history[-1]["created_at"] if history else "2026-03-15 10:00:00",
                    "last_message": history[-1]["content"] if history else "",
                    "message_count": len(history),
                }
            )
        return sessions[:limit]


class FakeLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return True

    @property
    def image_enabled(self) -> bool:
        return True

    def chat_text(self, system_prompt: str, user_prompt: str, temperature: float = 0.4):
        return None

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2):
        return None

    def choose_tool_call(self, system_prompt: str, user_prompt: str, tools, require_tool: bool = True):
        return None

    def generate_image(self, prompt: str, negative_prompt: str = ""):
        return {"url": "memory://generated.png", "model": "fake-image-model"}


class FakeImageGenerationTool:
    def __init__(self, llm: FakeLLMClient) -> None:
        self.llm = llm

    def run(self, poster_spec):
        return {
            "url": "memory://generated.png",
            "local_path": "image/generated_image_test.png",
            "file_name": "generated_image_test.png",
        }


class WorkflowRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            openai_api_key="test-key",
            openai_api_base="https://example.com/v1/",
            openai_model="fake-chat-model",
            openai_image_model="fake-image-model",
            enable_llm=True,
            enable_image_generation=True,
            database_url="sqlite://",
            image_size="1024x1024",
            image_cfg=4.0,
            image_steps=20,
            host="127.0.0.1",
            port=8000,
        )
        self.db_patcher = patch("app.runtime.workflow.DatabaseManager", FakeDatabaseManager)
        self.llm_patcher = patch("app.runtime.workflow.LLMClient", FakeLLMClient)
        self.image_patcher = patch("app.runtime.workflow.ImageGenerationTool", FakeImageGenerationTool)
        self.db_patcher.start()
        self.llm_patcher.start()
        self.image_patcher.start()
        self.workflow = MarketingWorkflow(self.settings)

    def tearDown(self) -> None:
        self.image_patcher.stop()
        self.llm_patcher.stop()
        self.db_patcher.stop()

    def test_copy_only_flow(self) -> None:
        response = self.workflow.handle_message("帮我写一条羊毛衫6折的广告文案")
        self.assertEqual(response.plan["tasks"], ["write_copy"])
        self.assertEqual(response.intent_type, "combined_task")
        self.assertTrue(response.ad_copy)
        self.assertFalse(response.tool_calls)
        self.assertStageOrder(response.execution_steps, ["supervisor", "planner", "executor", "writing_agent", "executor", "response"])

    def test_audience_selection_flow(self) -> None:
        response = self.workflow.handle_message("看看谁在关注羊毛衫")
        self.assertEqual(response.plan["tasks"], ["select_audience"])
        self.assertEqual(response.intent_type, "audience_query")
        self.assertGreaterEqual(len(response.target_users), 2)
        self.assertEqual(response.tool_calls[0]["tool_name"], "select_target_audience")
        self.assertIn("selection_reason", self._step_by_stage(response.execution_steps, "data_agent"))

    def test_single_user_analysis_and_copy_flow(self) -> None:
        response = self.workflow.handle_message("褚亦最近在看什么，帮我写一条广告文案")
        self.assertEqual(response.plan["tasks"], ["analyze_user", "write_copy"])
        self.assertEqual(response.tool_calls[0]["tool_name"], "query_user_profile")
        self.assertTrue(response.insight)
        self.assertTrue(response.ad_copy)
        self.assertIn("用户洞察", response.reply)

    def test_poster_generation_flow(self) -> None:
        response = self.workflow.handle_message("帮我做一张羊毛衫6折海报")
        self.assertEqual(response.plan["tasks"], ["prepare_poster", "generate_image"])
        self.assertEqual(response.intent_type, "poster_generation")
        self.assertTrue(response.poster_spec)
        self.assertTrue(response.generated_image)
        self.assertEqual(response.tool_calls[0]["tool_name"], "generate_marketing_image")
        self.assertIn("selection_reason", self._step_by_stage(response.execution_steps, "creative_agent"))

    def test_combined_marketing_flow(self) -> None:
        response = self.workflow.handle_message("上海地区最近谁在关注羊毛衫，顺便生成一版文案和海报")
        self.assertEqual(response.plan["tasks"], ["select_audience", "write_copy", "prepare_poster", "generate_image"])
        self.assertEqual(response.intent_type, "combined_task")
        self.assertTrue(response.target_users)
        self.assertTrue(response.ad_copy)
        self.assertTrue(response.poster_spec)
        self.assertTrue(response.generated_image)
        self.assertEqual([call["tool_name"] for call in response.tool_calls], ["select_target_audience", "generate_marketing_image"])

    def test_revision_and_approval_flow(self) -> None:
        session_id = "revision-case"
        first = self.workflow.handle_message("帮我写一条羊毛衫6折的广告文案", session_id=session_id)
        revised = self.workflow.handle_message("文案再柔和一点", session_id=session_id)
        approved = self.workflow.handle_message("可以了", session_id=session_id)

        self.assertTrue(first.ad_copy)
        self.assertEqual(revised.intent_type, "revision_request")
        self.assertEqual(revised.plan["tasks"], ["write_copy"])
        self.assertEqual(revised.memory["preference_memory"].get("copy_tone"), "soft")
        self.assertIn("已根据你的反馈重新调整结果", revised.reply)
        self.assertEqual(approved.intent_type, "revision_request")
        self.assertIn("已确认", approved.reply)
        self.assertIsNone(approved.memory["pending_artifact"])
        self.assertStageOrder(approved.execution_steps, ["supervisor", "response"])

    def assertStageOrder(self, steps, expected):
        self.assertEqual([step["stage"] for step in steps], expected)

    @staticmethod
    def _step_by_stage(steps, stage):
        for step in steps:
            if step.get("stage") == stage:
                return step
        raise AssertionError(f"未找到阶段 {stage}")


if __name__ == "__main__":
    unittest.main()
