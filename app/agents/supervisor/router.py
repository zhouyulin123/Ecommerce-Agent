import re
from typing import Any, Dict, List

from app.constants import AUDIENCE_SELECTION_NODE, COPYWRITING_NODE, EXECUTION_NODES, FEEDBACK_PARSER_NODE, IMAGE_GENERATION_NODE, POSTER_PROMPT_NODE, SQL_QUERY_NODE, USER_INSIGHT_NODE
from app.infra.database import DatabaseManager
from app.infra.llm import LLMClient
from app.prompts import load_prompt
from app.runtime.state import ConversationMemory
from app.utils.location import canonical_location, normalize_location_text, strip_location_whitespace


INTENT_SINGLE_USER_QUERY = "single_user_query"
INTENT_SINGLE_USER_AD = "single_user_ad"
INTENT_AUDIENCE_QUERY = "audience_query"
INTENT_POSTER = "poster_generation"
INTENT_COMBINED = "combined_task"
INTENT_REVISION = "revision_request"


class RouterAgent:
    def __init__(self, db: DatabaseManager, llm: LLMClient) -> None:
        self.db = db
        self.llm = llm
        self.prompt = load_prompt("router")

    def route(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        heuristic = self._heuristic_route(message, memory)
        heuristic_nodes = list(heuristic["next_nodes"])
        llm_result = self._llm_route(message, memory)
        if llm_result:
            heuristic.update({
                "intent_type": llm_result.get("intent_type", heuristic["intent_type"]),
                "entities": {**heuristic["entities"], **{key: value for key, value in (llm_result.get("entities") or {}).items() if value}},
                "next_nodes": llm_result.get("next_nodes") or heuristic["next_nodes"],
            })
        heuristic["has_user"] = bool((heuristic.get("entities") or {}).get("user_name"))
        if not heuristic.get("explicit_poster"):
            heuristic["next_nodes"] = [node for node in heuristic["next_nodes"] if node not in {POSTER_PROMPT_NODE, IMAGE_GENERATION_NODE}]
            if heuristic["intent_type"] == INTENT_POSTER:
                heuristic["intent_type"] = self._fallback_intent_without_poster(heuristic)
        heuristic["next_nodes"] = self._normalize_nodes(heuristic["intent_type"], heuristic["next_nodes"], heuristic.get("explicit_poster", False), heuristic.get("has_user", False))
        if not heuristic["next_nodes"]:
            heuristic["next_nodes"] = self._normalize_nodes(heuristic["intent_type"], heuristic_nodes, heuristic.get("explicit_poster", False), heuristic.get("has_user", False))
        return heuristic

    def _heuristic_route(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        entities = self._extract_entities(message, memory)
        explicit_poster = any(word in message for word in ["海报", "图片", "视觉", "生图", "poster"])
        wants_copy = any(word in message for word in ["广告", "文案", "推送语", "广告语", "标题", "营销", "宣传语"])
        wants_audience = any(word in message for word in ["推给谁", "给谁推送", "谁适合推送", "哪些人", "人群", "名单", "关注", "看过", "浏览", "买过"])
        has_user = bool(entities.get("user_name"))
        if explicit_poster and (wants_copy or wants_audience or has_user):
            intent = INTENT_COMBINED
        elif explicit_poster:
            intent = INTENT_POSTER
        elif has_user and wants_copy:
            intent = INTENT_SINGLE_USER_AD
        elif has_user:
            intent = INTENT_SINGLE_USER_QUERY
        elif wants_copy and wants_audience:
            intent = INTENT_COMBINED
        elif wants_audience:
            intent = INTENT_AUDIENCE_QUERY
        elif wants_copy:
            intent = INTENT_SINGLE_USER_AD if has_user else INTENT_COMBINED
        elif any(word in message for word in ["再来", "重写", "换一个", "改", "调整"]):
            intent = INTENT_REVISION
        else:
            intent = INTENT_AUDIENCE_QUERY if entities.get("product_name") else INTENT_SINGLE_USER_QUERY
        next_nodes: List[str] = []
        if intent == INTENT_SINGLE_USER_QUERY:
            next_nodes = [SQL_QUERY_NODE, USER_INSIGHT_NODE]
        elif intent == INTENT_SINGLE_USER_AD:
            next_nodes = [SQL_QUERY_NODE, USER_INSIGHT_NODE, COPYWRITING_NODE] if has_user else [COPYWRITING_NODE]
        elif intent == INTENT_AUDIENCE_QUERY:
            next_nodes = [AUDIENCE_SELECTION_NODE]
        elif intent == INTENT_POSTER:
            next_nodes = [POSTER_PROMPT_NODE, IMAGE_GENERATION_NODE]
        elif intent == INTENT_COMBINED:
            if has_user:
                next_nodes = [SQL_QUERY_NODE, USER_INSIGHT_NODE, COPYWRITING_NODE]
            else:
                if wants_audience:
                    next_nodes.append(AUDIENCE_SELECTION_NODE)
                if wants_copy:
                    next_nodes.append(COPYWRITING_NODE)
                if explicit_poster:
                    next_nodes.extend([POSTER_PROMPT_NODE, IMAGE_GENERATION_NODE])
        else:
            next_nodes = [FEEDBACK_PARSER_NODE]
        if "只要海报" in message:
            next_nodes = [POSTER_PROMPT_NODE, IMAGE_GENERATION_NODE]
            intent = INTENT_POSTER
        if "只要文案" in message:
            next_nodes = [COPYWRITING_NODE]
        return {"intent_type": intent, "entities": entities, "next_nodes": next_nodes, "explicit_poster": explicit_poster, "wants_copy": wants_copy, "wants_audience": wants_audience, "has_user": has_user}

    def _llm_route(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        payload = {"message": message, "history": [{"role": item.role, "content": item.content} for item in memory.history[-6:]], "last_entities": memory.last_entities, "pending_artifact": memory.pending_artifact}
        return self.llm.chat_json(self.prompt, str(payload)) or {}

    def _extract_entities(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        catalog = self.db.get_catalog()
        entities: Dict[str, Any] = {}
        is_follow_up = self._looks_like_follow_up(message)
        entities["user_name"] = self._match_longest(catalog["user_names"], message)
        entities["product_name"] = self._match_longest(catalog["product_names"], message)
        entities["location_scope"] = self._match_location(catalog["addresses"], message)
        discount_match = re.search(r"(\d+(?:\.\d+)?)\s*折", message)
        if discount_match:
            entities["discount"] = f"{discount_match.group(1)}折"
        else:
            full_cut = re.search(r"满\s*\d+\s*减\s*\d+", message)
            if full_cut:
                entities["discount"] = full_cut.group(0).replace(" ", "")
        if is_follow_up and not entities.get("user_name"):
            entities["user_name"] = memory.last_entities.get("user_name")
        if is_follow_up and not entities.get("product_name"):
            entities["product_name"] = memory.last_entities.get("product_name")
        if is_follow_up and not entities.get("location_scope") and any(word in message for word in ["本地", "这个区", "该地区"]):
            entities["location_scope"] = memory.last_entities.get("location_scope")
        return {key: value for key, value in entities.items() if value}

    @staticmethod
    def _fallback_intent_without_poster(route: Dict[str, Any]) -> str:
        if route.get("wants_copy") and route.get("wants_audience"):
            return INTENT_COMBINED
        if route.get("wants_audience"):
            return INTENT_AUDIENCE_QUERY
        if route.get("wants_copy"):
            return INTENT_SINGLE_USER_AD if route.get("has_user") else INTENT_COMBINED
        return INTENT_AUDIENCE_QUERY if route.get("entities", {}).get("product_name") else INTENT_SINGLE_USER_QUERY

    @staticmethod
    def _match_longest(candidates: List[str], message: str) -> str:
        matches = [item for item in candidates if item and item in message]
        return sorted(matches, key=len, reverse=True)[0] if matches else ""

    @staticmethod
    def _match_location(candidates: List[str], message: str) -> str:
        raw_message = strip_location_whitespace(message)
        normalized_message = normalize_location_text(raw_message)
        city_aliases: List[str] = []
        for item in sorted(candidates, key=len, reverse=True):
            raw_item = strip_location_whitespace(item)
            normalized_item = normalize_location_text(raw_item)
            collapsed_item = canonical_location(raw_item)
            if raw_item and raw_item in raw_message:
                return collapsed_item
            if normalized_item and normalized_item in normalized_message:
                return collapsed_item
            if collapsed_item and collapsed_item in raw_message:
                return collapsed_item
            city = RouterAgent._extract_city_scope(raw_item)
            if city:
                city_aliases.append(city)
        for city in sorted(set(city_aliases), key=len, reverse=True):
            if city in raw_message:
                return city
        return ""

    @staticmethod
    def _extract_city_scope(location: str) -> str:
        raw = strip_location_whitespace(location)
        if not raw:
            return ""
        if "市" in raw:
            return raw.split("市", 1)[0].replace("省", "").replace("自治区", "").replace("特别行政区", "")
        if "省" in raw:
            return raw.split("省", 1)[0]
        return ""

    @staticmethod
    def _looks_like_follow_up(message: str) -> bool:
        return any(marker in message for marker in ["这个", "这", "它", "上一个", "上一版", "刚才", "刚刚", "继续", "再来", "同样", "也给我", "这款"])

    @staticmethod
    def _normalize_nodes(intent_type: str, next_nodes: List[str], explicit_poster: bool, has_user: bool) -> List[str]:
        nodes = [node for node in next_nodes if node in EXECUTION_NODES or node == FEEDBACK_PARSER_NODE]
        if not has_user:
            nodes = [node for node in nodes if node not in {SQL_QUERY_NODE, USER_INSIGHT_NODE}]
        if intent_type == INTENT_SINGLE_USER_AD and COPYWRITING_NODE not in nodes:
            nodes.append(COPYWRITING_NODE)
        if explicit_poster and intent_type in {INTENT_POSTER, INTENT_COMBINED} and POSTER_PROMPT_NODE not in nodes:
            nodes.append(POSTER_PROMPT_NODE)
        if explicit_poster and intent_type in {INTENT_POSTER, INTENT_COMBINED} and IMAGE_GENERATION_NODE not in nodes:
            nodes.append(IMAGE_GENERATION_NODE)
        return nodes
