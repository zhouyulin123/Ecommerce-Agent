from typing import Any, Dict, List

from app.agents.supervisor.router import INTENT_AUDIENCE_QUERY, INTENT_COMBINED, INTENT_REVISION
from app.constants import TASK_GENERATE_IMAGE, TASK_SELECT_AUDIENCE
from app.runtime.state import AgentState, ConversationMemory


class ResponseAgent:
    def __init__(self, llm) -> None:
        self.llm = llm

    def compose(self, state: AgentState, memory: ConversationMemory) -> str:
        if state.error:
            return f"这一轮没有跑通，原因是: {state.error}"
        if state.feedback and state.feedback.get("is_approval"):
            return "已确认，当前结果将作为本轮最终版本保留。"
        lines: List[str] = []
        planned_tasks = (state.execution_plan or {}).get("tasks") or []
        if state.feedback and state.feedback.get("is_revision"):
            lines.append("已根据你的反馈重新调整结果。")
        if planned_tasks:
            lines.append(f"执行计划: {' -> '.join(planned_tasks)}")
        if state.insight:
            lines.append(f"用户洞察: {state.insight.get('summary', '')}")
        if state.target_users:
            sample = "、".join(self._format_target_user(item) for item in state.target_users[:10])
            lines.append(f"建议推送给这些用户: {sample}")
        elif state.intent_type in {INTENT_AUDIENCE_QUERY, INTENT_COMBINED} and TASK_SELECT_AUDIENCE in planned_tasks:
            lines.append("按当前条件没有查到可直接推送的用户，建议放宽地区或商品条件后再试。")
        if state.ad_copy:
            lines.append(f"广告语: {state.ad_copy.get('title', '')} / {state.ad_copy.get('subtitle', '')} / {state.ad_copy.get('cta', '')}")
        if state.poster_spec:
            lines.append(f"海报提示词已生成，建议配色: {state.poster_spec.get('color_palette', '')}")
        if state.generated_image and state.generated_image.get("local_path"):
            lines.append(f"图片已保存: {state.generated_image.get('local_path')}")
        elif TASK_GENERATE_IMAGE in planned_tasks and state.poster_spec:
            lines.append("图片生成未完成，可检查图片模型配置后重试。")
        if state.intent_type == INTENT_REVISION and not lines:
            return "已收到修改请求，但当前没有可重新生成的产物。"
        return "\n".join(lines)

    @staticmethod
    def _format_target_user(item: Dict[str, Any]) -> str:
        actions = []
        if item.get("buy_count"):
            actions.append(f"购买{item.get('buy_count', 0)}次")
        if item.get("view_count"):
            actions.append(f"浏览{item.get('view_count', 0)}次")
        detail = "/".join(actions) if actions else "无行为记录"
        return f"{item['user_name']}({item.get('address', '')}, {detail})"
