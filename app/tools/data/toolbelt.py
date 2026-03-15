from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.constants import DATA_AGENT
from app.runtime.state import ToolCallRecord
from app.tools.base import ToolDefinition, build_structured_tool
from app.tools.data.audience_selection import AudienceSelectionTool
from app.tools.data.sql_query import SQLQueryTool


class QueryUserProfileArgs(BaseModel):
    user_name: str = Field(description="需要分析的用户名")
    product_name: Optional[str] = Field(default=None, description="可选的商品名称，用于限定行为记录")


class SelectTargetAudienceArgs(BaseModel):
    entities: Dict[str, Any] = Field(default_factory=dict, description="圈人相关的实体条件")
    query_plan: Optional[Dict[str, Any]] = Field(default=None, description="规划器生成的查询计划")


class DataToolbelt:
    def __init__(self, sql_tool: SQLQueryTool, audience_tool: AudienceSelectionTool) -> None:
        self.sql_tool = sql_tool
        self.audience_tool = audience_tool
        self._definitions = {
            "query_user_profile": ToolDefinition(
                name="query_user_profile",
                owner_agent=DATA_AGENT,
                description="查询单个用户的基础信息，以及最近的浏览和购买行为。",
                when_to_use="当任务需要用户级洞察、个体分析或文案上下文时使用。",
                input_schema={"user_name": "字符串", "product_name": "字符串，可选"},
                output_schema={"user_info": "对象或空", "recent_views": "列表", "recent_buys": "列表"},
                failure_modes=["user_not_found"],
            ),
            "select_target_audience": ToolDefinition(
                name="select_target_audience",
                owner_agent=DATA_AGENT,
                description="基于校验后的筛选条件，从电商数据库中圈选目标人群。",
                when_to_use="当任务需要投放名单、触达对象或目标用户集合时使用。",
                input_schema={"entities": "字典", "query_plan": "字典，可选"},
                output_schema={"target_users": "列表"},
                failure_modes=["empty_result"],
            ),
        }
        self._tools = {
            "query_user_profile": build_structured_tool(
                definition=self._definitions["query_user_profile"],
                func=self._query_user_profile_tool,
                args_schema=QueryUserProfileArgs,
            ),
            "select_target_audience": build_structured_tool(
                definition=self._definitions["select_target_audience"],
                func=self._select_target_audience_tool,
                args_schema=SelectTargetAudienceArgs,
            ),
        }

    def definitions(self) -> List[ToolDefinition]:
        return list(self._definitions.values())

    def tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def invoke_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Tuple[Any, ToolCallRecord]:
        tool = self._tools.get(tool_name)
        if not tool:
            record = ToolCallRecord(
                owner_agent=DATA_AGENT,
                tool_name=tool_name,
                status="failed",
                input_payload=tool_input,
                output_keys=[],
                error="unsupported_tool",
            )
            fallback = [] if tool_name == "select_target_audience" else {"user_info": None, "recent_views": [], "recent_buys": []}
            return fallback, record
        try:
            result = tool.invoke(tool_input)
        except Exception:
            result = [] if tool_name == "select_target_audience" else {"user_info": None, "recent_views": [], "recent_buys": []}
        return self._build_record(tool_name, tool_input, result)

    def query_user_profile(self, entities: Dict[str, Any]) -> Tuple[Dict[str, Any], ToolCallRecord]:
        return self.invoke_tool(
            "query_user_profile",
            {"user_name": entities.get("user_name", ""), "product_name": entities.get("product_name")},
        )

    def select_target_audience(self, entities: Dict[str, Any], query_plan: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], ToolCallRecord]:
        return self.invoke_tool("select_target_audience", {"entities": entities, "query_plan": query_plan})

    def _query_user_profile_tool(self, user_name: str, product_name: Optional[str] = None) -> Dict[str, Any]:
        return self.sql_tool.run({"user_name": user_name, "product_name": product_name})

    def _select_target_audience_tool(
        self,
        entities: Dict[str, Any],
        query_plan: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self.audience_tool.run(entities, query_plan=query_plan or {})

    @staticmethod
    def _build_record(tool_name: str, tool_input: Dict[str, Any], result: Any) -> Tuple[Any, ToolCallRecord]:
        if tool_name == "query_user_profile":
            payload = result if isinstance(result, dict) else {"user_info": None, "recent_views": [], "recent_buys": []}
            record = ToolCallRecord(
                owner_agent=DATA_AGENT,
                tool_name=tool_name,
                status="success" if payload.get("user_info") else "empty",
                input_payload=tool_input,
                output_keys=sorted(payload.keys()),
                error=None if payload.get("user_info") else "user_not_found",
            )
            return payload, record
        rows = result if isinstance(result, list) else []
        record = ToolCallRecord(
            owner_agent=DATA_AGENT,
            tool_name=tool_name,
            status="success" if rows else "empty",
            input_payload=tool_input,
            output_keys=["target_users"],
            error=None if rows else "empty_result",
        )
        return rows, record
