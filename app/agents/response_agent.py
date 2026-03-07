from typing import List

from app.llm import LLMClient
from app.state import AgentState, ConversationMemory


class ResponseAgent:
    """最终回复节点：将结构化结果拼装为对用户友好的文本。"""

    def __init__(self, llm: LLMClient) -> None:
        """初始化回复节点，当前以规则模板输出为主。"""
        self.llm = llm

    def compose(self, state: AgentState, memory: ConversationMemory) -> str:
        """根据工作流状态生成最终回复文案。"""
        return self._fallback_reply(state)

    @staticmethod
    def _fallback_reply(state: AgentState) -> str:
        """规则化构建回复内容，确保输出稳定可控。"""
        if state.error:
            return f"这轮没有跑通，原因是：{state.error}"

        lines: List[str] = []

        if state.feedback and state.feedback.get("is_revision"):
            lines.append("已根据你的反馈重新调整结果。")

        if state.insight:
            lines.append(f"用户洞察：{state.insight.get('summary', '')}")

        if state.target_users:
            sample = "、".join(ResponseAgent._format_target_user(item) for item in state.target_users[:10])
            lines.append(f"建议推送给这些用户：{sample}")
        elif state.intent_type in {"audience_query", "combined_task"}:
            lines.append("按当前条件没有查到可直接推送的用户。建议放宽地区或商品条件后再查。")

        if state.ad_copy:
            lines.append(
                "广告语："
                f"{state.ad_copy.get('title', '')} / "
                f"{state.ad_copy.get('subtitle', '')} / "
                f"{state.ad_copy.get('cta', '')}"
            )

        if state.poster_spec:
            lines.append(f"海报提示词已生成，建议配色：{state.poster_spec.get('color_palette', '')}")

        if state.generated_image and state.generated_image.get("local_path"):
            lines.append(f"图片已保存：{state.generated_image.get('local_path')}")

        return "\n".join(lines)

    @staticmethod
    def _format_target_user(item: dict) -> str:
        """把目标用户记录格式化为紧凑展示文本。"""
        actions = []
        if item.get("buy_count"):
            actions.append(f"购买{item.get('buy_count', 0)}次")
        if item.get("view_count"):
            actions.append(f"浏览{item.get('view_count', 0)}次")
        detail = "/".join(actions) if actions else "无行为记录"
        return f"{item['user_name']}({item.get('address', '')}, {detail})"
