from collections import Counter
from typing import Any, Dict, List


class UserInsightNode:
    """用户洞察节点：将浏览/购买明细聚合成可用于营销的话术线索。"""

    def run(self, query_result: Dict[str, Any]) -> Dict[str, Any]:
        """从用户行为中提取兴趣品类、未转化商品和简要洞察。"""
        recent_views: List[Dict[str, Any]] = query_result.get("recent_views", [])
        recent_buys: List[Dict[str, Any]] = query_result.get("recent_buys", [])

        if not recent_views:
            return {
                "top_interest": "",
                "view_not_buy": [],
                "summary": "该用户近期没有可用浏览记录，暂时无法形成稳定偏好判断。",
            }

        view_counter = Counter(item["item_name"] for item in recent_views if item.get("item_name"))
        buy_counter = Counter(item["item_name"] for item in recent_buys if item.get("item_name"))
        top_interest = view_counter.most_common(1)[0][0]
        view_not_buy = [name for name, _ in view_counter.most_common() if buy_counter.get(name, 0) == 0]

        buy_text = "，且已购买过部分相关商品" if recent_buys else "，但近期还没有成交记录"
        if view_not_buy:
            summary = f"用户近期重点关注{top_interest}，多次浏览未转化商品包括{', '.join(view_not_buy[:3])}{buy_text}。"
        else:
            summary = f"用户近期重点关注{top_interest}，浏览与购买兴趣较一致{buy_text}。"

        return {
            "top_interest": top_interest,
            "view_not_buy": view_not_buy,
            "summary": summary,
            "view_counts": dict(view_counter),
            "buy_counts": dict(buy_counter),
        }
