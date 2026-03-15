import json
from typing import Any, Dict, Tuple

from app.agents.creative.poster_prompt import PosterPromptNode
from app.constants import CREATIVE_AGENT, TASK_GENERATE_IMAGE, TASK_PREPARE_POSTER
from app.infra.llm import LLMClient
from app.runtime.state import ConversationMemory
from app.tools.creative.toolbelt import CreativeToolbelt


class CreativeAgent:
    def __init__(self, llm: LLMClient, poster_node: PosterPromptNode, toolbelt: CreativeToolbelt) -> None:
        self.llm = llm
        self.poster_node = poster_node
        self.toolbelt = toolbelt

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        task = (state.get("task_queue") or [""])[0]
        trace = list(state.get("trace") or []) + [CREATIVE_AGENT]
        memory: ConversationMemory = state["memory"]
        if task == TASK_PREPARE_POSTER:
            entities = self._resolve_entities(state, memory)
            ad_copy = state.get("ad_copy") or memory.last_artifacts.get("ad_copy") or {}
            poster_spec = self.poster_node.run(entities, ad_copy, memory, state.get("feedback") or {})
            return {
                "active_agent": CREATIVE_AGENT,
                "entities": entities,
                "poster_spec": poster_spec,
                "task_queue": list((state.get("task_queue") or [])[1:]),
                "trace": trace,
            }
        if task == TASK_GENERATE_IMAGE:
            tool_name, tool_input = self._select_tool_for_task(state, memory)
            selection_reason = self._selection_reason(tool_name, state, memory)
            generated_image, tool_call = self.toolbelt.invoke_tool(tool_name, tool_input)
            return {
                "active_agent": CREATIVE_AGENT,
                "generated_image": generated_image,
                "tool_calls": list(state.get("tool_calls") or []) + [tool_call],
                "selection_reason": selection_reason,
                "task_queue": list((state.get("task_queue") or [])[1:]),
                "trace": trace,
            }
        return {"active_agent": CREATIVE_AGENT, "error": f"创意智能体收到不支持的任务: {task}", "task_queue": [], "trace": trace}

    @staticmethod
    def _resolve_entities(state: Dict[str, Any], memory: ConversationMemory) -> Dict[str, Any]:
        entities = dict(state.get("entities") or {})
        if not entities.get("product_name"):
            insight = state.get("insight") or memory.last_artifacts.get("insight") or {}
            entities["product_name"] = insight.get("top_interest") or memory.last_entities.get("product_name") or ""
        return entities

    def _select_tool_for_task(self, state: Dict[str, Any], memory: ConversationMemory) -> Tuple[str, Dict[str, Any]]:
        poster_spec = state.get("poster_spec") or memory.last_artifacts.get("poster_spec") or {}
        selected = self.llm.choose_tool_call(
            system_prompt=(
                "你是创意智能体，只能通过工具完成图片生成。"
                "当海报提示词已经准备好且当前任务需要出图时，调用 generate_marketing_image。"
                "不要输出自然语言，只返回一个工具调用。"
            ),
            user_prompt=json.dumps(
                {
                    "task": TASK_GENERATE_IMAGE,
                    "poster_spec": poster_spec,
                    "available_tools": self.toolbelt.tool_names(),
                },
                ensure_ascii=False,
            ),
            tools=self.toolbelt.tools(),
            require_tool=True,
        )
        selected_args = (selected or {}).get("args") or {}
        return "generate_marketing_image", {
            "poster_prompt": selected_args.get("poster_prompt") or poster_spec.get("poster_prompt", ""),
            "style_keywords": selected_args.get("style_keywords") or poster_spec.get("style_keywords"),
            "color_palette": selected_args.get("color_palette") or poster_spec.get("color_palette"),
        }

    @staticmethod
    def _selection_reason(tool_name: str, state: Dict[str, Any], memory: ConversationMemory) -> str:
        poster_spec = state.get("poster_spec") or memory.last_artifacts.get("poster_spec") or {}
        headline = poster_spec.get("headline") or poster_spec.get("poster_prompt") or "当前海报方案"
        return f"当前任务需要把海报方案转换为图片，且已有海报规格，因此调用 {tool_name}。参考方案: {str(headline)[:40]}"
