from typing import Any, Dict, List

from app.infra.llm import LLMClient
from app.prompts import load_prompt
from app.runtime.state import ConversationMemory


class PosterPromptNode:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.prompt = load_prompt("poster_prompt")

    def run(self, entities: Dict[str, Any], ad_copy: Dict[str, Any], memory: ConversationMemory, feedback: Dict[str, Any]) -> Dict[str, Any]:
        llm_result = self._llm_generate(entities, ad_copy, memory, feedback)
        if llm_result:
            return llm_result
        return self._fallback_generate(entities, ad_copy, memory, feedback)

    def _llm_generate(self, entities: Dict[str, Any], ad_copy: Dict[str, Any], memory: ConversationMemory, feedback: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"entities": entities, "ad_copy": ad_copy, "preference_memory": memory.preference_memory, "feedback": feedback, "previous_poster": memory.last_artifacts.get("poster_spec")}
        return self.llm.chat_json(self.prompt, str(payload)) or {}

    @staticmethod
    def _fallback_generate(entities: Dict[str, Any], ad_copy: Dict[str, Any], memory: ConversationMemory, feedback: Dict[str, Any]) -> Dict[str, Any]:
        product = entities.get("product_name") or "商品主视觉"
        discount = entities.get("discount", "")
        title = ad_copy.get("title", "")
        subtitle = ad_copy.get("subtitle", "")
        constraints = feedback.get("constraints", {})
        style_keywords: List[str] = ["电商海报", "高清", "商品主视觉"]
        if constraints.get("style") == "high_end" or memory.preference_memory.get("poster_style") == "high_end":
            style_keywords.extend(["高级感", "简约排版", "精致质感"])
        if constraints.get("color") == "warm" or memory.preference_memory.get("poster_color") == "warm":
            palette = "暖米色 + 橙金色"
            style_keywords.extend(["暖色调", "柔和光线"])
        else:
            palette = "高级灰 + 低饱和点缀" if "高级感" in style_keywords else "品牌主色 + 白底"
        visual_elements = [product, "促销标签", "价格信息区", "品牌标题区"]
        prompt = f"电商促销海报，主体为 {product}"
        if discount:
            prompt += f"，突出 {discount} 折扣信息"
        if title:
            prompt += f"，主标题为“{title}”"
        if subtitle:
            prompt += f"，副标题为“{subtitle}”"
        prompt += f"，整体风格 {', '.join(style_keywords[-3:])}，配色 {palette}，构图干净，适合电商营销图生成。"
        return {"poster_prompt": prompt, "visual_elements": visual_elements, "color_palette": palette, "style_keywords": style_keywords}
