from typing import Any, Dict, List, Optional, Tuple

from app.infra.database import DatabaseManager
from app.utils.location import normalize_location_text, sql_normalize_location


class AudienceSelectionTool:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def run(self, entities: Dict[str, Any], query_plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self._has_audience_filters(entities):
            return []
        nl2sql_rows = self._run_generated_sql(entities, query_plan)
        if nl2sql_rows is not None:
            return [self._normalize_row(row) for row in nl2sql_rows]
        return []

    def _run_generated_sql(self, entities: Dict[str, Any], query_plan: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
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
        normalized = dict(row)
        normalized["view_count"] = int(normalized.get("view_count") or 0)
        normalized["buy_count"] = int(normalized.get("buy_count") or 0)
        normalized["total_quantity"] = int(normalized.get("total_quantity") or 0)
        normalized["total_amount"] = float(normalized.get("total_amount") or 0.0)
        return normalized

    @staticmethod
    def _has_audience_filters(entities: Dict[str, Any]) -> bool:
        return bool(entities.get("product_name") or entities.get("location_scope") or entities.get("user_name"))

    @staticmethod
    def _build_sql_params(entities: Dict[str, Any], limit: int) -> Dict[str, Any]:
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
    def _build_location_filter(location_scope: str, address_column: str) -> Tuple[str, Dict[str, Any]]:
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
