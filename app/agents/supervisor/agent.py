from typing import Any, Dict, List

from app.agents.supervisor.feedback_parser import FeedbackParserAgent
from app.agents.supervisor.message_parser import MessageParserAgent
from app.agents.supervisor.router import INTENT_REVISION, RouterAgent
from app.constants import LEGACY_NODE_TO_TASK, TASK_GENERATE_IMAGE, TASK_PREPARE_POSTER, TASK_WRITE_COPY
from app.runtime.state import ConversationMemory


class SupervisorAgent:
    def __init__(self, feedback_parser: FeedbackParserAgent, message_parser: MessageParserAgent, router: RouterAgent) -> None:
        self.feedback_parser = feedback_parser
        self.message_parser = message_parser
        self.router = router

    def inspect(self, request: str, memory: ConversationMemory) -> Dict[str, Any]:
        feedback = self.feedback_parser.parse(request, memory)
        parsed_message = self.message_parser.parse(request, memory)
        if feedback.get("is_approval"):
            return {"mode": "approval", "intent_type": INTENT_REVISION, "feedback": feedback, "parsed_message": parsed_message, "entities": dict(memory.last_entities), "requested_tasks": []}
        if feedback.get("is_revision"):
            return {"mode": "revision", "intent_type": INTENT_REVISION, "feedback": feedback, "parsed_message": parsed_message, "entities": dict(memory.last_entities), "requested_tasks": self._revision_tasks(feedback)}
        route = self.router.route(request, memory)
        merged_entities = dict(route.get("entities") or {})
        for key, value in (parsed_message.get("entities") or {}).items():
            if value and not merged_entities.get(key):
                merged_entities[key] = value
        return {"mode": "plan", "intent_type": route.get("intent_type", ""), "feedback": feedback, "parsed_message": {**parsed_message, "entities": merged_entities}, "entities": merged_entities, "requested_tasks": self._route_tasks(route.get("next_nodes") or [])}

    @staticmethod
    def _route_tasks(legacy_nodes: List[str]) -> List[str]:
        seen = set()
        tasks: List[str] = []
        for node_name in legacy_nodes:
            task = LEGACY_NODE_TO_TASK.get(node_name)
            if task and task not in seen:
                tasks.append(task)
                seen.add(task)
        return tasks

    @staticmethod
    def _revision_tasks(feedback: Dict[str, Any]) -> List[str]:
        target = feedback.get("target_artifact")
        if target == "ad_copy":
            return [TASK_WRITE_COPY]
        if target == "poster":
            return [TASK_PREPARE_POSTER, TASK_GENERATE_IMAGE]
        return []
