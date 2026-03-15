from typing import Any, Dict

from app.infra.llm import LLMClient
from app.prompts import load_prompt
from app.runtime.state import ConversationMemory


class MessageParserAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.prompt = load_prompt("message_parser")

    def parse(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        payload = {
            "message": message,
            "last_entities": memory.last_entities,
            "pending_artifact": memory.pending_artifact,
            "history": [{"role": item.role, "content": item.content} for item in memory.history[-6:]],
        }
        result = self.llm.chat_json(self.prompt, str(payload)) or {}
        return self._normalize_result(result, message)

    @staticmethod
    def _normalize_result(result: Dict[str, Any], fallback_message: str) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {}
        normalized_message = result.get("normalized_message")
        parsed["normalized_message"] = normalized_message.strip() if isinstance(normalized_message, str) and normalized_message.strip() else fallback_message
        intent_hint = result.get("intent_hint")
        if isinstance(intent_hint, str) and intent_hint.strip():
            parsed["intent_hint"] = intent_hint.strip()
        entities = result.get("entities") or {}
        if isinstance(entities, dict):
            allowed_entities: Dict[str, Any] = {}
            for key in ("user_name", "product_name", "location_scope", "discount"):
                value = entities.get(key)
                if isinstance(value, str):
                    value = value.strip()
                if value:
                    allowed_entities[key] = value
            parsed["entities"] = allowed_entities
        constraints = result.get("constraints") or {}
        if isinstance(constraints, dict):
            compact_constraints: Dict[str, Any] = {}
            for key in ("must_include", "must_exclude", "tone", "style"):
                value = constraints.get(key)
                if value:
                    compact_constraints[key] = value
            if compact_constraints:
                parsed["constraints"] = compact_constraints
        return parsed
