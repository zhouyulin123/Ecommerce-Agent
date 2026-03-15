from typing import Any, Dict, List

from app.agents.planner.query_planner import QueryPlannerAgent
from app.agents.supervisor.router import INTENT_REVISION
from app.constants import TASK_GENERATE_IMAGE, TASK_PREPARE_POSTER
from app.runtime.state import ConversationMemory


class PlannerAgent:
    def __init__(self, query_planner: QueryPlannerAgent) -> None:
        self.query_planner = query_planner

    def build_plan(self, request: str, intent_type: str, entities: Dict[str, Any], memory: ConversationMemory, requested_tasks: List[str]) -> Dict[str, Any]:
        task_queue = self._normalize_tasks(requested_tasks)
        query_plan = {}
        if intent_type != INTENT_REVISION:
            query_plan = self.query_planner.plan(request, intent_type, entities, memory)
        execution_plan = {"intent_type": intent_type, "tasks": task_queue, "query_goal": query_plan.get("query_goal"), "query_mode": query_plan.get("query_mode")}
        return {"execution_plan": execution_plan, "query_plan": query_plan, "task_queue": task_queue}

    @staticmethod
    def _normalize_tasks(tasks: List[str]) -> List[str]:
        ordered: List[str] = []
        seen = set()
        for task in tasks:
            if task and task not in seen:
                ordered.append(task)
                seen.add(task)
        if TASK_GENERATE_IMAGE in seen and TASK_PREPARE_POSTER not in seen:
            ordered.insert(ordered.index(TASK_GENERATE_IMAGE), TASK_PREPARE_POSTER)
        return ordered
