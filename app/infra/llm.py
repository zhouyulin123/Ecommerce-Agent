import json
import re
from typing import Any, Dict, List, Optional
from urllib import error, request

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from app.infra.config import Settings


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        """Create text and image model clients from the shared runtime settings."""
        self.settings = settings
        self.client = None
        if self.enabled:
            self.client = ChatOpenAI(
                model=self.settings.openai_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_api_base,
                temperature=0.4,
            )

    @property
    def enabled(self) -> bool:
        """Tell callers whether text-model features are available."""
        return self.settings.llm_enabled

    @property
    def image_enabled(self) -> bool:
        """Tell callers whether image generation can be executed."""
        return self.settings.image_enabled

    def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
    ) -> Optional[str]:
        """Run a plain text LLM call and return the raw assistant content."""
        if not self.client:
            return None
        try:
            response = self.client.bind(temperature=temperature).invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
        except Exception:
            return None
        return getattr(response, "content", None)

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> Optional[Dict[str, Any]]:
        """Run an LLM call that is expected to return a JSON object."""
        text = self.chat_text(system_prompt, user_prompt, temperature=temperature)
        if not text:
            return None
        parsed = self._extract_json(text)
        return parsed if isinstance(parsed, dict) else None

    def choose_tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[BaseTool],
        require_tool: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Use LangChain tool calling to let the model select one tool."""
        if not self.client or not tools:
            return None
        try:
            response = self.client.bind_tools(
                tools,
                tool_choice="required" if require_tool else "auto",
            ).invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
        except Exception:
            return None
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return None
        selected = tool_calls[0]
        return {
            "name": selected.get("name", ""),
            "args": selected.get("args") or {},
            "id": selected.get("id", ""),
        }

    def generate_image(self, prompt: str, negative_prompt: str = "") -> Optional[Dict[str, Any]]:
        """Call the image endpoint and return normalized generation metadata."""
        if not self.image_enabled:
            return None

        payload: Dict[str, Any] = {
            "model": self.settings.openai_image_model,
            "prompt": prompt,
            "image_size": self.settings.image_size,
            "num_inference_steps": self.settings.image_steps,
            "cfg": self.settings.image_cfg,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        req = request.Request(
            self.settings.openai_api_base + "images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openai_api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=90) as resp:
                content = json.loads(resp.read().decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, ValueError):
            return None

        images = content.get("images") or []
        first = images[0] if images else {}
        image_url = first.get("url")
        if not image_url:
            return None

        return {
            "url": image_url,
            "model": self.settings.openai_image_model,
            "image_size": self.settings.image_size,
            "cfg": self.settings.image_cfg,
            "num_inference_steps": self.settings.image_steps,
            "seed": content.get("seed"),
            "timings": content.get("timings"),
        }

    @staticmethod
    def _extract_json(content: str) -> Optional[Dict[str, Any]]:
        """Extract the first valid JSON object from a model response."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.S)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
