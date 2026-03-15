import re
from typing import Any, Dict, List

from app.infra.database import DatabaseManager
from app.infra.llm import LLMClient
from app.prompts import load_prompt
from app.runtime.state import ConversationMemory
from app.utils.location import sql_normalize_location


class QueryPlannerAgent:
    def __init__(self, db: DatabaseManager, llm: LLMClient) -> None:
        self.db = db
        self.llm = llm
        self.prompt = load_prompt("query_planner")
        self.sql_prompt = load_prompt("query_sql")

    def plan(self, message: str, intent_type: str, entities: Dict[str, Any], memory: ConversationMemory) -> Dict[str, Any]:
        plan = self._heuristic_plan(message, intent_type, entities)
        llm_result = self._llm_plan(message, intent_type, entities, memory)
        if llm_result:
            filters = dict(plan["filters"])
            for key, value in (llm_result.get("filters") or {}).items():
                if value and not filters.get(key):
                    filters[key] = value
            plan.update(
                {
                    "query_goal": llm_result.get("query_goal", plan["query_goal"]),
                    "tables": llm_result.get("tables") or plan["tables"],
                    "filters": filters,
                    "behavior_scope": llm_result.get("behavior_scope") or plan["behavior_scope"],
                    "limit": llm_result.get("limit") or plan["limit"],
                    "sort_by": llm_result.get("sort_by") or plan["sort_by"],
                }
            )
        plan["query_goal"] = self._normalize_query_goal(plan.get("query_goal"))
        plan["query_goal"] = self._coerce_query_goal(plan["query_goal"], intent_type, bool((plan.get("filters") or {}).get("user_name")))
        plan["tables"] = self._normalize_tables(plan.get("tables") or [])
        plan["behavior_scope"] = self._normalize_behaviors(plan.get("behavior_scope") or [])
        plan["limit"] = self._normalize_limit(plan.get("limit"))
        nl2sql_payload = self._llm_sql(message, plan, memory)
        if nl2sql_payload.get("query_mode") == "restricted_nl2sql":
            plan.update(nl2sql_payload)
        elif plan.get("query_goal") in {"audience_selection", "audience_and_poster", "general_marketing_lookup"}:
            fallback_payload = self._fallback_sql(plan)
            if nl2sql_payload.get("sql_validation_error"):
                fallback_payload["sql_validation_error"] = nl2sql_payload["sql_validation_error"]
            plan.update(fallback_payload)
        return plan

    def _heuristic_plan(self, message: str, intent_type: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        wants_poster = any(token in message for token in ["海报", "图片", "生图"])
        wants_audience = any(token in message for token in ["推送", "给谁", "人群", "名单", "关注", "看过", "浏览", "买过"])
        if entities.get("user_name"):
            query_goal = "single_user_profile"
        elif wants_poster and wants_audience:
            query_goal = "audience_and_poster"
        elif wants_poster:
            query_goal = "poster_only"
        elif wants_audience:
            query_goal = "audience_selection"
        else:
            query_goal = "general_marketing_lookup"
        behavior_scope = self._infer_behaviors(message, entities)
        tables: List[str] = ["User_info"]
        if "browse" in behavior_scope:
            tables.append("User_logs")
        if "buy" in behavior_scope:
            tables.append("User_Buy")
        if entities.get("user_name") and "User_logs" not in tables:
            tables.append("User_logs")
        if entities.get("user_name") and "User_Buy" not in tables:
            tables.append("User_Buy")
        return {
            "query_goal": query_goal,
            "intent_type": intent_type,
            "tables": tables,
            "filters": {"user_name": entities.get("user_name"), "product_name": entities.get("product_name"), "location_scope": entities.get("location_scope"), "discount": entities.get("discount")},
            "behavior_scope": behavior_scope,
            "limit": 20,
            "sort_by": "buy_then_view_then_recency",
            "query_mode": "safe_template",
        }

    def _llm_plan(self, message: str, intent_type: str, entities: Dict[str, Any], memory: ConversationMemory) -> Dict[str, Any]:
        payload = {"message": message, "intent_type": intent_type, "entities": entities, "memory_last_entities": memory.last_entities, "schema": self.db.get_schema_overview()}
        return self.llm.chat_json(self.prompt, str(payload)) or {}

    def _llm_sql(self, message: str, plan: Dict[str, Any], memory: ConversationMemory) -> Dict[str, Any]:
        if plan.get("query_goal") not in {"audience_selection", "audience_and_poster", "general_marketing_lookup"}:
            return {}
        payload = {"message": message, "plan": plan, "memory_last_entities": memory.last_entities, "schema": self.db.get_schema_overview()}
        result = self.llm.chat_json(self.sql_prompt, str(payload)) or {}
        sql = (result.get("sql") or "").strip()
        if not sql:
            return {}
        validation_error = self._validate_select_sql(sql, plan.get("tables") or [])
        if validation_error:
            return {"sql_validation_error": validation_error}
        return {"query_mode": "restricted_nl2sql", "generated_sql": sql.rstrip(";"), "sql_source": "llm", "sql_validation_error": None}

    def _fallback_sql(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        filters = plan.get("filters") or {}
        browse_filters = self._sql_filters(filters, "ul.browse_item", "ui.user_name")
        buy_filters = self._sql_filters(filters, "ub.buy_item", "ui.user_name")
        sql = f"""
            SELECT user_id, user_name, address,
                   SUM(CASE WHEN event_type = 'browse' THEN 1 ELSE 0 END) AS view_count,
                   MAX(CASE WHEN event_type = 'browse' THEN event_time END) AS last_view_time,
                   SUM(CASE WHEN event_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
                   MAX(CASE WHEN event_type = 'buy' THEN event_time END) AS last_buy_time,
                   SUM(quantity) AS total_quantity,
                   SUM(order_amount) AS total_amount
            FROM (
                SELECT ui.user_id, ui.user_name, ui.address, 'browse' AS event_type, ul.enter_time AS event_time, 0 AS quantity, 0.0 AS order_amount
                FROM User_logs ul JOIN User_info ui ON ul.user_id = ui.user_id
                WHERE 1 = 1 {browse_filters}
                UNION ALL
                SELECT ui.user_id, ui.user_name, ui.address, 'buy' AS event_type, ub.enter_time AS event_time, ub.quantity AS quantity, ub.order_amount AS order_amount
                FROM User_Buy ub JOIN User_info ui ON ub.user_id = ui.user_id
                WHERE 1 = 1 {buy_filters}
            ) AS audience_events
            GROUP BY user_id, user_name, address
            ORDER BY buy_count DESC, view_count DESC,
                     GREATEST(COALESCE(last_buy_time, '1000-01-01 00:00:00'), COALESCE(last_view_time, '1000-01-01 00:00:00')) DESC
            LIMIT :limit
        """.strip()
        return {"query_mode": "restricted_nl2sql", "generated_sql": sql, "sql_source": "planner_fallback", "sql_validation_error": None}

    @staticmethod
    def _sql_filters(filters: Dict[str, Any], item_column: str, user_column: str) -> str:
        clauses: List[str] = []
        if filters.get("product_name"):
            clauses.append(f"AND {item_column} = :product_name")
        if filters.get("user_name"):
            clauses.append(f"AND {user_column} = :user_name")
        if filters.get("location_scope"):
            clauses.append("AND (ui.address LIKE :location_scope_raw OR " + f"{sql_normalize_location('ui.address')} LIKE :location_scope_normalized)")
        return "\n                ".join(clauses)

    @staticmethod
    def _infer_behaviors(message: str, entities: Dict[str, Any]) -> List[str]:
        explicit_browse = any(token in message for token in ["看过", "浏览", "关注"])
        explicit_buy = any(token in message for token in ["买过", "购买", "下单", "成交"])
        if explicit_browse and explicit_buy:
            return ["browse", "buy"]
        if explicit_browse:
            return ["browse"]
        if explicit_buy:
            return ["buy"]
        return ["browse", "buy"]

    @staticmethod
    def _normalize_tables(tables: List[str]) -> List[str]:
        valid = {"User_info", "User_logs", "User_Buy"}
        return [table for table in tables if table in valid]

    @staticmethod
    def _normalize_behaviors(behaviors: List[str]) -> List[str]:
        valid = [item for item in behaviors if item in {"browse", "buy"}]
        return valid or ["browse", "buy"]

    @staticmethod
    def _normalize_limit(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 20
        return min(max(parsed, 1), 50)

    @staticmethod
    def _normalize_query_goal(value: Any) -> str:
        raw = str(value or "").strip().lower()
        mapping = {"find_target_users": "audience_selection", "find_target_users_for_promotion": "audience_selection", "find_potential_customers": "audience_selection", "target_user_selection": "audience_selection", "target_users": "audience_selection", "promotion_audience": "audience_selection", "audience_and_copy": "audience_selection", "user_profile_query": "single_user_profile", "single_user_lookup": "single_user_profile", "poster_with_audience": "audience_and_poster"}
        return mapping.get(raw, raw or "general_marketing_lookup")

    @staticmethod
    def _coerce_query_goal(query_goal: str, intent_type: str, has_user: bool) -> str:
        supported = {"single_user_profile", "audience_selection", "audience_and_poster", "poster_only", "general_marketing_lookup"}
        if query_goal in supported:
            return query_goal
        if has_user:
            return "single_user_profile"
        if intent_type in {"audience_query", "combined_task"}:
            return "audience_selection"
        if intent_type == "poster_generation":
            return "audience_and_poster"
        return "general_marketing_lookup"

    @staticmethod
    def _validate_select_sql(sql: str, planned_tables: List[str]) -> str:
        cleaned = sql.strip().strip(";").strip()
        lowered = cleaned.lower()
        if not lowered.startswith("select "):
            return "只允许使用 SELECT 查询语句"
        if ";" in cleaned:
            return "只允许执行一条 SQL 语句"
        blocked_keywords = {"insert", "update", "delete", "drop", "alter", "create", "truncate", "replace", "grant", "revoke", "call", "execute", "show", "desc", "describe"}
        for keyword in blocked_keywords:
            if re.search(rf"\b{keyword}\b", lowered):
                return f"SQL 包含被禁止的关键字: {keyword}"
        referenced_tables = {table for table in re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", cleaned, flags=re.I)}
        allowed_tables = {"User_info", "User_logs", "User_Buy"}
        if not referenced_tables:
            return "SQL 必须引用至少一张业务表"
        if any(table not in allowed_tables for table in referenced_tables):
            return "SQL 引用了未授权的数据表"
        if planned_tables and any(table not in planned_tables for table in referenced_tables):
            return "SQL 引用了计划之外的数据表"
        if not all(alias in cleaned for alias in ["user_name", "address"]):
            return "SQL 结果必须包含 user_name 和 address 字段"
        return ""
