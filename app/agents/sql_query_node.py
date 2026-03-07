from typing import Any, Dict

from app.database import DatabaseManager


class SQLQueryNode:
    def __init__(self, db: DatabaseManager) -> None:
        """Store the database handle used for named-user lookups."""
        self.db = db

    def run(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch one user's profile plus recent browse and purchase history."""
        user_name = entities.get("user_name")
        if not user_name:
            return {"user_info": None, "recent_views": [], "recent_buys": []}

        user_info = self.db.query_one(
            """
            SELECT user_id, user_name, phone, address
            FROM User_info
            WHERE user_name = :user_name
            LIMIT 1
            """,
            {"user_name": user_name},
        )
        if not user_info:
            return {"user_info": None, "recent_views": [], "recent_buys": []}

        product_name = entities.get("product_name")
        recent_views_sql = """
            SELECT browse_item AS item_name, shop_name, enter_time, exit_time
            FROM User_logs
            WHERE user_name = :user_name
            {product_filter}
            ORDER BY enter_time DESC
            LIMIT 10
        """
        recent_buys_sql = """
            SELECT buy_item AS item_name, shop_name, enter_time, exit_time, quantity, order_amount
            FROM User_Buy
            WHERE user_name = :user_name
            {product_filter}
            ORDER BY enter_time DESC
            LIMIT 10
        """
        params = {"user_name": user_name}
        if product_name:
            params["product_name"] = product_name

        recent_views = self.db.query_rows(
            recent_views_sql.format(product_filter="AND browse_item = :product_name" if product_name else ""),
            params,
        )
        recent_buys = self.db.query_rows(
            recent_buys_sql.format(product_filter="AND buy_item = :product_name" if product_name else ""),
            params,
        )
        return {
            "user_info": user_info,
            "recent_views": recent_views,
            "recent_buys": recent_buys,
        }
