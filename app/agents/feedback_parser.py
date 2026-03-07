from typing import Any, Dict

from app.llm import LLMClient
from app.prompts import load_prompt
from app.state import ConversationMemory


class FeedbackParserAgent:
    def __init__(self, llm: LLMClient) -> None:
        """Prepare the parser that distinguishes new tasks from revision feedback."""
        self.llm = llm
        self.prompt = load_prompt("feedback_parser")

    def parse(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        """Combine heuristic and LLM signals into one feedback classification result."""
        heuristic = self._heuristic_parse(message, memory)
        llm_result = self._llm_parse(message, memory)
        if llm_result:
            heuristic.update(llm_result)
            if "constraints" in llm_result and isinstance(llm_result["constraints"], dict):
                heuristic["constraints"].update(llm_result["constraints"])
        return heuristic

    def _heuristic_parse(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        """Detect approval/revision intent and extract reusable style constraints."""
        target_artifact = ""
        normalized = message.strip()
        lowered = normalized.lower()
        revision_keywords = ["不好", "不喜欢", "太", "改", "换", "重写", "重新", "再来", "优化", "调整"]
        approval_phrases = {
            "可以",
            "可以了",
            "就这样",
            "就这样吧",
            "通过",
            "满意",
            "满意了",
            "很好",
            "挺好",
            "不错",
            "这版可以",
            "这版不错",
        }

        if any(word in normalized for word in ["海报", "图片", "图", "视觉", "颜色", "排版"]):
            target_artifact = "poster"
        elif any(word in normalized for word in ["文案", "广告", "标题", "副标题", "cta", "推送"]):
            target_artifact = "ad_copy"
        elif memory.pending_artifact:
            target_artifact = memory.pending_artifact
        elif memory.last_artifacts.get("poster_spec"):
            target_artifact = "poster"
        elif memory.last_artifacts.get("ad_copy"):
            target_artifact = "ad_copy"

        looks_like_new_task = self._looks_like_new_task(normalized)
        is_approval = normalized in approval_phrases
        is_revision = any(word in normalized for word in revision_keywords)
        is_feedback = bool(target_artifact and not looks_like_new_task and (is_approval or is_revision))

        constraints = {
            "raw_feedback": normalized,
            "tone": "soft" if any(word in lowered for word in ["柔和", "温和", "自然", "别太硬"]) else "",
            "style": "high_end" if any(word in lowered for word in ["高级", "质感", "简约"]) else "",
            "color": "warm" if any(word in lowered for word in ["暖色", "偏暖", "橙", "米色"]) else "",
            "avoid": "hard_sell" if any(word in lowered for word in ["别太促销", "别太硬", "别喊口号"]) else "",
        }
        constraints = {key: value for key, value in constraints.items() if value}

        return {
            "is_feedback": is_feedback,
            "is_revision": is_feedback and is_revision,
            "is_approval": is_feedback and is_approval and not is_revision,
            "target_artifact": target_artifact,
            "constraints": constraints,
        }

    @staticmethod
    def _looks_like_new_task(message: str) -> bool:
        """Detect whether the user is starting a fresh request instead of giving feedback."""
        request_markers = [
            "帮我",
            "帮忙",
            "请",
            "麻烦",
            "查一下",
            "查下",
            "看一下",
            "看下",
            "看看",
            "查询",
            "筛一下",
            "筛选",
            "做一张",
            "做个",
            "生成",
            "给我",
            "可以帮我",
            "能不能",
        ]
        return any(marker in message for marker in request_markers)

    def _llm_parse(self, message: str, memory: ConversationMemory) -> Dict[str, Any]:
        """Ask the model to refine feedback classification using recent session history."""
        payload = {
            "message": message,
            "pending_artifact": memory.pending_artifact,
            "last_artifacts": list(memory.last_artifacts.keys()),
            "history": [{"role": item.role, "content": item.content} for item in memory.history[-6:]],
        }
        return self.llm.chat_json(self.prompt, str(payload)) or {}
