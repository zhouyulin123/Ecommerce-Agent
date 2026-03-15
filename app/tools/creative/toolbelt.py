from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.constants import CREATIVE_AGENT
from app.runtime.state import ToolCallRecord
from app.tools.base import ToolDefinition, build_structured_tool
from app.tools.creative.image_generation import ImageGenerationTool


class GenerateMarketingImageArgs(BaseModel):
    poster_prompt: str = Field(description="用于生成海报图片的完整提示词")
    style_keywords: Optional[List[str]] = Field(default=None, description="可选的风格关键词")
    color_palette: Optional[str] = Field(default=None, description="可选的颜色方案")


class CreativeToolbelt:
    def __init__(self, image_tool: ImageGenerationTool) -> None:
        self.image_tool = image_tool
        self._definitions = {
            "generate_marketing_image": ToolDefinition(
                name="generate_marketing_image",
                owner_agent=CREATIVE_AGENT,
                description="根据海报规格生成营销图片，并在需要时下载到本地。",
                when_to_use="只有在海报提示词已经准备好，且任务明确要求出图时才调用。",
                input_schema={"poster_prompt": "字符串", "style_keywords": "字符串列表，可选", "color_palette": "字符串，可选"},
                output_schema={"url": "字符串或空", "local_path": "字符串或空", "file_name": "字符串或空"},
                failure_modes=["image_generation_failed"],
            )
        }
        self._tools = {
            "generate_marketing_image": build_structured_tool(
                definition=self._definitions["generate_marketing_image"],
                func=self._generate_marketing_image_tool,
                args_schema=GenerateMarketingImageArgs,
            )
        }

    def definitions(self) -> List[ToolDefinition]:
        return list(self._definitions.values())

    def tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def invoke_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Tuple[Dict[str, Any], ToolCallRecord]:
        tool = self._tools.get(tool_name)
        if not tool:
            record = ToolCallRecord(
                owner_agent=CREATIVE_AGENT,
                tool_name=tool_name,
                status="failed",
                input_payload=tool_input,
                output_keys=[],
                error="unsupported_tool",
            )
            return {}, record
        try:
            result = tool.invoke(tool_input)
        except Exception:
            result = {}
        record = ToolCallRecord(
            owner_agent=CREATIVE_AGENT,
            tool_name=tool_name,
            status="success" if result.get("url") else "failed",
            input_payload=tool_input,
            output_keys=sorted(result.keys()),
            error=None if result.get("url") else "image_generation_failed",
        )
        return result, record

    def generate_marketing_image(self, poster_spec: Dict[str, Any]) -> Tuple[Dict[str, Any], ToolCallRecord]:
        return self.invoke_tool(
            "generate_marketing_image",
            {
                "poster_prompt": poster_spec.get("poster_prompt", ""),
                "style_keywords": poster_spec.get("style_keywords"),
                "color_palette": poster_spec.get("color_palette"),
            },
        )

    def _generate_marketing_image_tool(
        self,
        poster_prompt: str,
        style_keywords: Optional[List[str]] = None,
        color_palette: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.image_tool.run(
            {
                "poster_prompt": poster_prompt,
                "style_keywords": style_keywords or [],
                "color_palette": color_palette or "",
            }
        )
