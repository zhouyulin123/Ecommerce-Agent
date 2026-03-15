from typing import Any, Dict

from app.agents.writing.copywriting import CopywritingNode
from app.constants import TASK_WRITE_COPY, WRITING_AGENT
from app.runtime.state import ConversationMemory


class WritingAgent:
    def __init__(self, copy_node: CopywritingNode) -> None:
        self.copy_node = copy_node

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        task = (state.get("task_queue") or [""])[0]
        if task != TASK_WRITE_COPY:
            return {
                "active_agent": WRITING_AGENT,
                "error": f"写作智能体收到不支持的任务: {task}",
                "task_queue": [],
                "trace": list(state.get('trace') or []) + [WRITING_AGENT],
            }
        memory: ConversationMemory = state["memory"]
        entities = self._resolve_entities(state, memory)
        insight = state.get("insight") or memory.last_artifacts.get("insight") or {}
        ad_copy = self.copy_node.run(entities, insight, memory, state.get("feedback") or {})
        return {
            "active_agent": WRITING_AGENT,
            "entities": entities,
            "ad_copy": ad_copy,
            "task_queue": list((state.get("task_queue") or [])[1:]),
            "trace": list(state.get("trace") or []) + [WRITING_AGENT],
        }

    @staticmethod
    def _resolve_entities(state: Dict[str, Any], memory: ConversationMemory) -> Dict[str, Any]:
        entities = dict(state.get("entities") or {})
        if not entities.get("product_name"):
            insight = state.get("insight") or memory.last_artifacts.get("insight") or {}
            entities["product_name"] = insight.get("top_interest") or memory.last_entities.get("product_name") or ""
        return entities
