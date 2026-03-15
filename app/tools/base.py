from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Type

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    owner_agent: str
    description: str
    when_to_use: str
    input_schema: Dict[str, str]
    output_schema: Dict[str, str]
    failure_modes: List[str] = field(default_factory=list)

    def render_description(self) -> str:
        input_text = "；".join(f"{key}: {value}" for key, value in self.input_schema.items()) or "无"
        output_text = "；".join(f"{key}: {value}" for key, value in self.output_schema.items()) or "无"
        failure_text = "；".join(self.failure_modes) or "无"
        return (
            f"{self.description}\n"
            f"使用时机：{self.when_to_use}\n"
            f"输入：{input_text}\n"
            f"输出：{output_text}\n"
            f"失败模式：{failure_text}"
        )


def build_structured_tool(
    definition: ToolDefinition,
    func: Callable[..., Any],
    args_schema: Type[BaseModel],
) -> BaseTool:
    return StructuredTool.from_function(
        func=func,
        name=definition.name,
        description=definition.render_description(),
        args_schema=args_schema,
    )
