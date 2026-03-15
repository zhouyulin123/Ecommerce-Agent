import json
from typing import Any, Dict, Tuple

from app.agents.data.insight import UserInsightNode
from app.constants import DATA_AGENT, TASK_ANALYZE_USER, TASK_SELECT_AUDIENCE
from app.infra.llm import LLMClient
from app.tools.data.toolbelt import DataToolbelt


class DataAgent:
    def __init__(self, llm: LLMClient, toolbelt: DataToolbelt, insight_node: UserInsightNode) -> None:
        self.llm = llm
        self.toolbelt = toolbelt
        self.insight_node = insight_node

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        task = (state.get("task_queue") or [""])[0]
        update: Dict[str, Any] = {"active_agent": DATA_AGENT, "trace": list(state.get("trace") or []) + [DATA_AGENT]}
        if task == TASK_ANALYZE_USER:
            tool_name, tool_input = self._select_tool_for_task(task, state)
            update["selection_reason"] = self._selection_reason(task, tool_name, state)
            query_result, tool_call = self.toolbelt.invoke_tool(tool_name, tool_input)
            update["tool_calls"] = list(state.get("tool_calls") or []) + [tool_call]
            update["query_result"] = query_result
            update["task_queue"] = list((state.get("task_queue") or [])[1:])
            if not query_result.get("user_info"):
                update["error"] = "未查到该用户。"
                update["task_queue"] = []
                return update
            update["insight"] = self.insight_node.run(query_result)
            return update
        if task == TASK_SELECT_AUDIENCE:
            tool_name, tool_input = self._select_tool_for_task(task, state)
            update["selection_reason"] = self._selection_reason(task, tool_name, state)
            target_users, tool_call = self.toolbelt.invoke_tool(tool_name, tool_input)
            update["tool_calls"] = list(state.get("tool_calls") or []) + [tool_call]
            update["target_users"] = target_users
            update["task_queue"] = list((state.get("task_queue") or [])[1:])
            return update
        return {**update, "error": f"数据智能体收到不支持的任务: {task}", "task_queue": []}

    def _select_tool_for_task(self, task: str, state: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        selected = self.llm.choose_tool_call(
            system_prompt=(
                "你是数据智能体，只能通过工具完成任务。"
                "如果任务是单用户分析，选择 query_user_profile。"
                "如果任务是人群圈选、投放名单或目标用户筛选，选择 select_target_audience。"
                "不要输出自然语言，只返回一个工具调用。"
            ),
            user_prompt=json.dumps(
                {
                    "task": task,
                    "entities": state.get("entities") or {},
                    "query_plan": state.get("query_plan") or {},
                    "available_tools": self.toolbelt.tool_names(),
                },
                ensure_ascii=False,
            ),
            tools=self.toolbelt.tools(),
            require_tool=True,
        )
        tool_name = (selected or {}).get("name") or self._default_tool_name(task)
        if not self._tool_matches_task(task, tool_name):
            tool_name = self._default_tool_name(task)
        tool_input = self._build_tool_input(tool_name, state, (selected or {}).get("args") or {})
        return tool_name, tool_input

    @staticmethod
    def _default_tool_name(task: str) -> str:
        return "select_target_audience" if task == TASK_SELECT_AUDIENCE else "query_user_profile"

    @staticmethod
    def _tool_matches_task(task: str, tool_name: str) -> bool:
        if task == TASK_ANALYZE_USER:
            return tool_name == "query_user_profile"
        if task == TASK_SELECT_AUDIENCE:
            return tool_name == "select_target_audience"
        return False

    @staticmethod
    def _build_tool_input(tool_name: str, state: Dict[str, Any], selected_args: Dict[str, Any]) -> Dict[str, Any]:
        entities = dict(state.get("entities") or {})
        if tool_name == "query_user_profile":
            return {
                "user_name": selected_args.get("user_name") or entities.get("user_name", ""),
                "product_name": selected_args.get("product_name") or entities.get("product_name"),
            }
        merged_entities = dict(entities)
        merged_entities.update({key: value for key, value in (selected_args.get("entities") or {}).items() if value})
        return {
            "entities": merged_entities,
            "query_plan": selected_args.get("query_plan") or state.get("query_plan") or {},
        }

    @staticmethod
    def _selection_reason(task: str, tool_name: str, state: Dict[str, Any]) -> str:
        entities = state.get("entities") or {}
        if task == TASK_ANALYZE_USER:
            user_name = entities.get("user_name") or "目标用户"
            return f"当前任务是单用户分析，且已识别到用户 {user_name}，因此调用 {tool_name}。"
        product_name = entities.get("product_name") or "目标商品"
        location_scope = entities.get("location_scope")
        if location_scope:
            return f"当前任务需要按商品和地区圈选人群，已识别到 {product_name} / {location_scope}，因此调用 {tool_name}。"
        return f"当前任务需要圈选目标人群，已识别到商品 {product_name}，因此调用 {tool_name}。"
