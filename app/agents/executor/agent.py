from typing import Dict, List

from app.constants import CREATIVE_AGENT, DATA_AGENT, RESPONSE_AGENT, TASK_TO_AGENT, WRITING_AGENT


class Executor:
    def next_agent(self, task_queue: List[str]) -> str:
        if not task_queue:
            return RESPONSE_AGENT
        return TASK_TO_AGENT.get(task_queue[0], RESPONSE_AGENT)

    def route_map(self) -> Dict[str, str]:
        return {DATA_AGENT: "data_agent", WRITING_AGENT: "writing_agent", CREATIVE_AGENT: "creative_agent", RESPONSE_AGENT: "response"}
