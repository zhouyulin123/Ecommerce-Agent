from typing import Any, Dict

from app.llm import LLMClient
from app.prompts import load_prompt
from app.state import ConversationMemory


class CopywritingNode:
    """广告文案节点：先用大模型生成，不可用时走规则兜底。"""

    def __init__(self, llm: LLMClient) -> None:
        """初始化文案节点并加载对应提示词模板。"""
        self.llm = llm
        self.prompt = load_prompt("copywriting")

    def run(
        self,
        entities: Dict[str, Any],
        insight: Dict[str, Any],
        memory: ConversationMemory,
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成标准化文案结构：`title/subtitle/cta`。"""
        llm_result = self._normalize_copy_result(
            self._llm_generate(entities, insight, memory, feedback)
        )
        if llm_result:
            return llm_result
        return self._fallback_generate(entities, insight, memory, feedback)

    def _llm_generate(
        self,
        entities: Dict[str, Any],
        insight: Dict[str, Any],
        memory: ConversationMemory,
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将上下文打包后调用 LLM，获取结构化文案结果。"""
        payload = {
            "entities": entities,
            "insight": insight,
            "preference_memory": memory.preference_memory,
            "feedback": feedback,
            "previous_copy": memory.last_artifacts.get("ad_copy"),
        }
        return self.llm.chat_json(self.prompt, str(payload)) or {}

    @staticmethod
    def _normalize_copy_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """兼容中英文字段名，统一并清洗为标准文案结构。"""
        if not result:
            return {}
        title = result.get("title") or result.get("标题") or ""
        subtitle = (
            result.get("subtitle")
            or result.get("小标题")
            or result.get("副标题")
            or result.get("文案")
            or ""
        )
        cta = result.get("cta") or result.get("行动号召") or result.get("按钮文案") or "立即查看"
        normalized = {
            "title": str(title).strip(),
            "subtitle": str(subtitle).strip(),
            "cta": str(cta).strip(),
        }
        if not normalized["title"] and not normalized["subtitle"]:
            return {}
        return normalized

    @staticmethod
    def _fallback_generate(
        entities: Dict[str, Any],
        insight: Dict[str, Any],
        memory: ConversationMemory,
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """规则兜底：在无 LLM 或返回异常时保证仍能产出可用文案。"""
        product = entities.get("product_name") or insight.get("top_interest") or "精选好物"
        discount = entities.get("discount", "")
        location = entities.get("location_scope", "")
        tone_pref = feedback.get("constraints", {}).get("tone") or memory.preference_memory.get("copy_tone", "")
        avoid_hard_sell = feedback.get("constraints", {}).get("avoid") == "hard_sell"

        if discount and location:
            title = f"{location}{product}{discount}优惠"
            subtitle = f"{location}相关用户可优先触达，活动窗口期适合立即推送。"
        elif discount:
            title = f"{product}{discount}限时优惠"
            subtitle = f"{product}活动已上线，现在触达更容易带来转化。"
        elif location:
            title = f"{location}{product}现货提醒"
            subtitle = f"{location}{product}相关需求可重点触达，适合做一轮精准推送。"
        elif insight.get("view_not_buy"):
            title = f"你关注的{product}有新动态"
            subtitle = f"结合近期浏览偏好，{product}值得再看一看。"
        else:
            title = f"{product}上新提醒"
            subtitle = f"围绕{product}做一次简洁触达，适合当前营销任务。"

        if tone_pref == "soft" or avoid_hard_sell:
            subtitle = subtitle.replace("立即推送", "优先沟通").replace("值得再看一看", "可以再了解一下")

        return {
            "title": title[:18],
            "subtitle": subtitle[:35],
            "cta": "立即查看" if not avoid_hard_sell else "了解详情",
        }
