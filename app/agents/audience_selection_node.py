from typing import Any, Dict, List, Optional

from app.database import DatabaseManager
from app.utils.location import normalize_location_text, sql_normalize_location


class AudienceSelectionNode:
    def __init__(self, db: DatabaseManager) -> None:
        """初始化目标人群查询节点。"""
        self.db = db

    def run(self, entities: Dict[str, Any], query_plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """合并浏览与购买行为，返回按优先级排序的人群列表。"""
        if not self._has_audience_filters(entities):
            return []

        nl2sql_rows = self._run_generated_sql(entities, query_plan)
        if nl2sql_rows is not None:
            return [self._normalize_row(row) for row in nl2sql_rows]

        behavior_scope = self._resolve_behavior_scope(query_plan)
        browse_select = ""
        browse_params: Dict[str, Any] = {}
        buy_select = ""
        buy_params: Dict[str, Any] = {}
        union_keyword = ""

        if "browse" in behavior_scope:
            browse_filters, browse_params = self._build_behavior_filters(
                entities,
                item_column="ul.browse_item",
                user_column="ui.user_name",
                address_column="ui.address",
            )
            browse_select = """
                SELECT
                    ui.user_id,
                    ui.user_name,
                    ui.address,
                    'browse' AS event_type,
                    ul.enter_time AS event_time,
                    0 AS quantity,
                    0.0 AS order_amount
                FROM User_logs ul
                JOIN User_info ui ON ul.user_id = ui.user_id
                WHERE 1 = 1
                {browse_filters}
            """
        if "buy" in behavior_scope:
            buy_filters, buy_params = self._build_behavior_filters(
                entities,
                item_column="ub.buy_item",
                user_column="ui.user_name",
                address_column="ui.address",
            )
            buy_select = """
                SELECT
                    ui.user_id,
                    ui.user_name,
                    ui.address,
                    'buy' AS event_type,
                    ub.enter_time AS event_time,
                    ub.quantity AS quantity,
                    ub.order_amount AS order_amount
                FROM User_Buy ub
                JOIN User_info ui ON ub.user_id = ui.user_id
                WHERE 1 = 1
                {buy_filters}
            """
        if browse_select and buy_select:
            union_keyword = "\n\n                UNION ALL\n"

        sql = """
            SELECT
                user_id,
                user_name,
                address,
                SUM(CASE WHEN event_type = 'browse' THEN 1 ELSE 0 END) AS view_count,
                MAX(CASE WHEN event_type = 'browse' THEN event_time END) AS last_view_time,
                SUM(CASE WHEN event_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
                MAX(CASE WHEN event_type = 'buy' THEN event_time END) AS last_buy_time,
                SUM(quantity) AS total_quantity,
                SUM(order_amount) AS total_amount
            FROM (
                {browse_select}
                {union_keyword}
                {buy_select}
            ) AS audience_events
            GROUP BY user_id, user_name, address
            ORDER BY
                buy_count DESC,
                view_count DESC,
                GREATEST(
                    COALESCE(last_buy_time, '1000-01-01 00:00:00'),
                    COALESCE(last_view_time, '1000-01-01 00:00:00')
                ) DESC
            LIMIT 20
        """
        params = {**browse_params, **buy_params}
        rows = self.db.query_rows(
            sql.format(
                browse_select=browse_select.format(browse_filters=browse_filters) if browse_select else "",
                union_keyword=union_keyword,
                buy_select=buy_select.format(buy_filters=buy_filters) if buy_select else "",
            ),
            params,
        )
        return [self._normalize_row(row) for row in rows]

    def _run_generated_sql(
        self,
        entities: Dict[str, Any],
        query_plan: Optional[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        """执行受限 NL2SQL 生成的查询语句。"""
        plan = query_plan or {}
        if plan.get("query_mode") != "restricted_nl2sql":
            return None
        sql = (plan.get("generated_sql") or "").strip()
        if not sql:
            return None
        params = self._build_sql_params(entities, int(plan.get("limit") or 20))
        try:
            return self.db.query_rows(sql, params)
        except Exception:
            return None

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """把聚合列转成稳定类型，避免前端显示异常。"""
        normalized = dict(row)
        normalized["view_count"] = int(normalized.get("view_count") or 0)
        normalized["buy_count"] = int(normalized.get("buy_count") or 0)
        normalized["total_quantity"] = int(normalized.get("total_quantity") or 0)
        normalized["total_amount"] = float(normalized.get("total_amount") or 0.0)
        return normalized

    @staticmethod
    def _has_audience_filters(entities: Dict[str, Any]) -> bool:
        """避免在无约束条件下扫描全表。"""
        return bool(entities.get("product_name") or entities.get("location_scope") or entities.get("user_name"))

    @staticmethod
    def _build_behavior_filters(
        entities: Dict[str, Any],
        item_column: str,
        user_column: str,
        address_column: str,
    ) -> tuple[str, Dict[str, Any]]:
        """把结构化实体转成 SQL 过滤片段与绑定参数。"""
        filters: List[str] = []
        params: Dict[str, Any] = {}

        product_name = entities.get("product_name")
        if product_name:
            params["product_name"] = product_name
            filters.append(f"AND {item_column} = :product_name")

        user_name = entities.get("user_name")
        if user_name:
            params["user_name"] = user_name
            filters.append(f"AND {user_column} = :user_name")

        location_scope = entities.get("location_scope")
        if location_scope:
            location_clause, location_params = AudienceSelectionNode._build_location_filter(location_scope, address_column)
            filters.append(location_clause)
            params.update(location_params)

        return "\n                ".join(filters), params

    @staticmethod
    def _resolve_behavior_scope(query_plan: Optional[Dict[str, Any]]) -> List[str]:
        """从 query_plan 中读取行为范围，空值回退到 browse+buy。"""
        planned = list((query_plan or {}).get("behavior_scope") or [])
        valid = [item for item in planned if item in {"browse", "buy"}]
        return valid or ["browse", "buy"]

    @staticmethod
    def _build_sql_params(entities: Dict[str, Any], limit: int) -> Dict[str, Any]:
        """构建受限 NL2SQL 允许使用的参数字典。"""
        location_scope = (entities.get("location_scope") or "").strip().replace(" ", "")
        normalized_location = normalize_location_text(location_scope)
        return {
            "user_name": entities.get("user_name"),
            "product_name": entities.get("product_name"),
            "location_scope_raw": f"%{location_scope}%" if location_scope else None,
            "location_scope_normalized": f"%{normalized_location}%" if normalized_location else None,
            "limit": min(max(int(limit), 1), 50),
        }

    @staticmethod
    def _build_location_filter(location_scope: str, address_column: str) -> tuple[str, Dict[str, Any]]:
        """构建地区原始匹配+归一化匹配的联合过滤条件。"""
        raw = (location_scope or "").strip().replace(" ", "")
        normalized = normalize_location_text(raw)
        if not raw and not normalized:
            return "", {}

        params: Dict[str, Any] = {}
        clauses: List[str] = []
        if raw:
            params["location_scope_raw"] = f"%{raw}%"
            clauses.append(f"{address_column} LIKE :location_scope_raw")
        if normalized:
            params["location_scope_normalized"] = f"%{normalized}%"
            clauses.append(f"{sql_normalize_location(address_column)} LIKE :location_scope_normalized")
        return f"AND ({' OR '.join(clauses)})", params

    @staticmethod
    def _normalize_location_text(location_scope: str) -> str:
        """暴露地址归一化接口（兼容外部调用）。"""
        return normalize_location_text(location_scope)

    @staticmethod
    def _sql_normalize_location(address_column: str) -> str:
        """暴露 SQL 侧地址归一化表达式（兼容外部调用）。"""
        return sql_normalize_location(address_column)
