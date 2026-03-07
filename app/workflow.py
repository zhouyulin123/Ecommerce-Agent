import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.audience_selection_node import AudienceSelectionNode
from app.agents.copywriting_node import CopywritingNode
from app.agents.feedback_parser import FeedbackParserAgent
from app.agents.image_generation_node import ImageGenerationNode
from app.agents.message_parser_agent import MessageParserAgent
from app.agents.poster_prompt_node import PosterPromptNode
from app.agents.query_planner_agent import QueryPlannerAgent
from app.agents.response_agent import ResponseAgent
from app.agents.router_agent import (
    INTENT_AUDIENCE_QUERY,
    INTENT_COMBINED,
    INTENT_POSTER,
    INTENT_REVISION,
    RouterAgent,
)
from app.agents.sql_query_node import SQLQueryNode
from app.agents.user_insight_node import UserInsightNode
from app.config import Settings
from app.constants import (
    AUDIENCE_SELECTION_NODE,
    COPYWRITING_NODE,
    FEEDBACK_PARSER_NODE,
    IMAGE_GENERATION_NODE,
    MESSAGE_PARSER_NODE,
    POSTER_PROMPT_NODE,
    QUERY_PLANNER_NODE,
    ROUTER_AGENT_NODE,
    SQL_QUERY_NODE,
    USER_INSIGHT_NODE,
)
from app.database import DatabaseManager
from app.llm import LLMClient
from app.state import AgentState, ChatMessage, ChatResponse, ConversationMemory


class WorkflowGraphState(TypedDict, total=False):
    session_id: str
    request: str
    memory: ConversationMemory
    feedback: Dict[str, Any]
    parsed_message: Dict[str, Any]
    intent_type: str
    entities: Dict[str, Any]
    remaining_nodes: List[str]
    query_result: Dict[str, Any]
    query_plan: Dict[str, Any]
    insight: Dict[str, Any]
    target_users: List[Dict[str, Any]]
    ad_copy: Dict[str, Any]
    poster_spec: Dict[str, Any]
    generated_image: Dict[str, Any]
    response_text: str
    error: str
    trace: List[str]


class MarketingWorkflow:
    def __init__(self, settings: Settings) -> None:
        """初始化工作流与所有 Agent 依赖。"""
        self.settings = settings
        self.db = DatabaseManager(settings)
        self.db.bootstrap()
        self.llm = LLMClient(settings)

        self.feedback_parser = FeedbackParserAgent(self.llm)
        self.message_parser = MessageParserAgent(self.llm)
        self.router = RouterAgent(self.db, self.llm)
        self.query_planner = QueryPlannerAgent(self.db, self.llm)
        self.sql_node = SQLQueryNode(self.db)
        self.insight_node = UserInsightNode()
        self.audience_node = AudienceSelectionNode(self.db)
        self.copy_node = CopywritingNode(self.llm)
        self.poster_node = PosterPromptNode(self.llm)
        self.image_node = ImageGenerationNode(self.llm)
        self.response_agent = ResponseAgent(self.llm)
        self.graph = self._build_graph()

    def _build_graph(self):
        """定义 LangGraph 拓扑：反馈 -> 解析 -> 路由 -> 规划 -> 执行。"""
        graph = StateGraph(WorkflowGraphState)
        graph.add_node("feedback_parser", self._feedback_parser_step)
        graph.add_node("message_parser", self._message_parser_step)
        graph.add_node("revision_dispatch", self._revision_dispatch_step)
        graph.add_node("router", self._router_step)
        graph.add_node("query_planner", self._query_planner_step)
        graph.add_node("dispatch", self._dispatch_step)
        graph.add_node("sql_query", self._sql_query_step)
        graph.add_node("user_insight", self._user_insight_step)
        graph.add_node("audience_selection", self._audience_selection_step)
        graph.add_node("copywriting", self._copywriting_step)
        graph.add_node("poster_prompt", self._poster_prompt_step)
        graph.add_node("image_generation", self._image_generation_step)
        graph.add_node("response", self._response_step)

        graph.add_edge(START, "feedback_parser")
        graph.add_conditional_edges(
            "feedback_parser",
            self._after_feedback,
            {
                "approval": "response",
                "revision": "revision_dispatch",
                "route": "message_parser",
            },
        )
        graph.add_edge("message_parser", "router")
        graph.add_edge("revision_dispatch", "dispatch")
        graph.add_edge("router", "query_planner")
        graph.add_edge("query_planner", "dispatch")
        graph.add_conditional_edges(
            "dispatch",
            self._dispatch_next,
            {
                "sql_query": "sql_query",
                "user_insight": "user_insight",
                "audience_selection": "audience_selection",
                "copywriting": "copywriting",
                "poster_prompt": "poster_prompt",
                "image_generation": "image_generation",
                "response": "response",
            },
        )
        graph.add_edge("sql_query", "dispatch")
        graph.add_edge("user_insight", "dispatch")
        graph.add_edge("audience_selection", "dispatch")
        graph.add_edge("copywriting", "dispatch")
        graph.add_edge("poster_prompt", "dispatch")
        graph.add_edge("image_generation", "dispatch")
        graph.add_edge("response", END)
        return graph.compile()

    def handle_message(self, message: str, session_id: str = "") -> ChatResponse:
        """处理一轮会话并落库保存上下文。"""
        active_session_id = session_id or str(uuid.uuid4())
        memory = self.db.load_memory(active_session_id)
        self.db.append_message(active_session_id, "user", message)
        memory.history.append(ChatMessage(role="user", content=message))

        initial_state: WorkflowGraphState = {
            "session_id": active_session_id,
            "request": message,
            "memory": memory,
            "entities": {},
            "remaining_nodes": [],
            "target_users": [],
            "trace": [],
        }
        result = self.graph.invoke(initial_state)
        agent_state = self._to_agent_state(result)
        self._finalize(memory, agent_state)
        return self._build_response(agent_state, memory)

    def _feedback_parser_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """识别本轮是新任务、确认还是修改请求。"""
        feedback = self.feedback_parser.parse(state["request"], state["memory"])
        update: Dict[str, Any] = {
            "feedback": feedback,
            "trace": self._append_trace(state, FEEDBACK_PARSER_NODE),
        }
        if feedback.get("is_approval"):
            update["intent_type"] = INTENT_REVISION
        return update

    @staticmethod
    def _after_feedback(state: WorkflowGraphState) -> str:
        """根据反馈结果决定后续分支。"""
        feedback = state.get("feedback") or {}
        if feedback.get("is_approval"):
            return "approval"
        if feedback.get("is_revision"):
            return "revision"
        return "route"

    def _message_parser_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """把原始消息解析成结构化提示，便于调试观察。"""
        parsed_message = self.message_parser.parse(state["request"], state["memory"])
        return {
            "parsed_message": parsed_message,
            "trace": self._append_trace(state, MESSAGE_PARSER_NODE),
        }

    def _revision_dispatch_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """将“修改请求”映射到可重生成的节点。"""
        memory = state["memory"]
        feedback = state.get("feedback") or {}
        self._merge_preferences(memory, feedback)

        target = feedback.get("target_artifact")
        if target == "ad_copy":
            remaining_nodes = [COPYWRITING_NODE]
        elif target == "poster":
            remaining_nodes = [POSTER_PROMPT_NODE, IMAGE_GENERATION_NODE]
        else:
            remaining_nodes = []

        update: Dict[str, Any] = {
            "intent_type": INTENT_REVISION,
            "entities": dict(memory.last_entities),
            "remaining_nodes": remaining_nodes,
        }
        if not remaining_nodes:
            update["error"] = "当前反馈没有对应到可修改的海报或文案结果。"
        return update

    def _router_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """执行路由决策，得到意图、实体和执行节点。"""
        route = self.router.route(state["request"], state["memory"])
        parsed_message = dict(state.get("parsed_message") or {})
        parsed_entities = dict(parsed_message.get("entities") or {})
        for key, value in (route.get("entities") or {}).items():
            if value and not parsed_entities.get(key):
                parsed_entities[key] = value
        if parsed_entities:
            parsed_message["entities"] = parsed_entities

        return {
            "intent_type": route["intent_type"],
            "entities": route["entities"],
            "remaining_nodes": route["next_nodes"],
            "parsed_message": parsed_message,
            "trace": self._append_trace(state, ROUTER_AGENT_NODE),
        }

    def _query_planner_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """生成 schema 感知的查询计划。"""
        query_plan = self.query_planner.plan(
            state["request"],
            state.get("intent_type", ""),
            state.get("entities") or {},
            state["memory"],
        )
        return {
            "query_plan": query_plan,
            "trace": self._append_trace(state, QUERY_PLANNER_NODE),
        }

    @staticmethod
    def _dispatch_step(state: WorkflowGraphState) -> Dict[str, Any]:
        """占位节点：触发下一步节点重新选择。"""
        return {}

    def _dispatch_next(self, state: WorkflowGraphState) -> str:
        """把业务节点名映射为 LangGraph 边名称。"""
        if state.get("error") or not state.get("remaining_nodes"):
            return "response"
        mapping = {
            SQL_QUERY_NODE: "sql_query",
            USER_INSIGHT_NODE: "user_insight",
            AUDIENCE_SELECTION_NODE: "audience_selection",
            COPYWRITING_NODE: "copywriting",
            POSTER_PROMPT_NODE: "poster_prompt",
            IMAGE_GENERATION_NODE: "image_generation",
        }
        return mapping.get(state["remaining_nodes"][0], "response")

    def _sql_query_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """查询单用户画像与行为明细。"""
        query_result = self.sql_node.run(state.get("entities") or {})
        update: Dict[str, Any] = {
            "query_result": query_result,
            "remaining_nodes": self._consume_node(state, SQL_QUERY_NODE),
            "trace": self._append_trace(state, SQL_QUERY_NODE),
        }
        if not query_result.get("user_info"):
            update["error"] = "未查到该用户。"
            update["remaining_nodes"] = []
        return update

    def _user_insight_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """把用户行为明细聚合为营销洞察。"""
        return {
            "insight": self.insight_node.run(state.get("query_result") or {}),
            "remaining_nodes": self._consume_node(state, USER_INSIGHT_NODE),
            "trace": self._append_trace(state, USER_INSIGHT_NODE),
        }

    def _audience_selection_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """查询符合条件的目标人群。"""
        return {
            "target_users": self.audience_node.run(
                state.get("entities") or {},
                query_plan=state.get("query_plan") or {},
            ),
            "remaining_nodes": self._consume_node(state, AUDIENCE_SELECTION_NODE),
            "trace": self._append_trace(state, AUDIENCE_SELECTION_NODE),
        }

    def _copywriting_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """生成广告文案。"""
        preloaded = self._hydrate_copy_context(state)
        ad_copy = self.copy_node.run(
            preloaded.get("entities") or {},
            preloaded.get("insight") or {},
            preloaded["memory"],
            preloaded.get("feedback") or {},
        )
        return {
            **preloaded,
            "ad_copy": ad_copy,
            "remaining_nodes": self._consume_node(preloaded, COPYWRITING_NODE),
            "trace": self._append_trace(preloaded, COPYWRITING_NODE),
        }

    def _poster_prompt_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """生成海报提示词；缺少文案时先补生成文案。"""
        preloaded = self._hydrate_copy_context(state)
        ad_copy = preloaded.get("ad_copy") or preloaded["memory"].last_artifacts.get("ad_copy")
        extra_trace: List[str] = []
        if not ad_copy:
            ad_copy = self.copy_node.run(
                preloaded.get("entities") or {},
                preloaded.get("insight") or {},
                preloaded["memory"],
                preloaded.get("feedback") or {},
            )
            extra_trace.append(COPYWRITING_NODE)

        poster_spec = self.poster_node.run(
            preloaded.get("entities") or {},
            ad_copy or {},
            preloaded["memory"],
            preloaded.get("feedback") or {},
        )
        return {
            **preloaded,
            "ad_copy": ad_copy,
            "poster_spec": poster_spec,
            "remaining_nodes": self._consume_node(preloaded, POSTER_PROMPT_NODE),
            "trace": self._append_trace(preloaded, *(extra_trace + [POSTER_PROMPT_NODE])),
        }

    def _image_generation_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """调用生图节点生成最终图片。"""
        generated_image = self.image_node.run(state.get("poster_spec") or {})
        return {
            "generated_image": generated_image,
            "remaining_nodes": self._consume_node(state, IMAGE_GENERATION_NODE),
            "trace": self._append_trace(state, IMAGE_GENERATION_NODE),
        }

    def _response_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """做结果校验并产出最终回复文本。"""
        intent_type = state.get("intent_type", "")
        error = state.get("error")
        if intent_type == INTENT_AUDIENCE_QUERY and not state.get("target_users") and not error:
            error = "按当前条件没有找到可直接推送的用户。"
        if intent_type == INTENT_POSTER and not state.get("poster_spec") and not error:
            error = "海报提示词生成失败。"
        if intent_type == INTENT_COMBINED and not any(
            [state.get("target_users"), state.get("ad_copy"), state.get("poster_spec"), state.get("generated_image")]
        ) and not error:
            error = "组合任务没有产出可用结果。"

        response_state = dict(state)
        if error:
            response_state["error"] = error
        response_text = self.response_agent.compose(self._to_agent_state(response_state), state["memory"])
        return {"error": error, "response_text": response_text}

    def _hydrate_copy_context(self, state: WorkflowGraphState) -> Dict[str, Any]:
        """为文案/海报节点补齐必要上下文（洞察、商品等）。"""
        hydrated = dict(state)
        memory = hydrated["memory"]
        entities = dict(hydrated.get("entities") or {})
        query_result = hydrated.get("query_result")
        insight = hydrated.get("insight") or memory.last_artifacts.get("insight")

        if not query_result and entities.get("user_name"):
            query_result = self.sql_node.run(entities)
            hydrated["query_result"] = query_result
        if not insight and query_result and query_result.get("user_info"):
            insight = self.insight_node.run(query_result)
            hydrated["insight"] = insight
        if not entities.get("product_name"):
            entities["product_name"] = (insight or {}).get("top_interest") or memory.last_entities.get("product_name") or ""
        hydrated["entities"] = entities
        return hydrated

    @staticmethod
    def _consume_node(state: WorkflowGraphState, node_name: str) -> List[str]:
        """消费已执行节点，返回剩余待执行节点。"""
        remaining = list(state.get("remaining_nodes") or [])
        if remaining and remaining[0] == node_name:
            return remaining[1:]
        return remaining

    @staticmethod
    def _append_trace(state: WorkflowGraphState, *node_names: str) -> List[str]:
        """记录本轮执行轨迹，便于排查与调试。"""
        trace = list(state.get("trace") or [])
        trace.extend(node_names)
        return trace

    @staticmethod
    def _merge_preferences(memory: ConversationMemory, feedback: Dict[str, Any]) -> None:
        """把用户反馈中的可复用偏好写入会话记忆。"""
        constraints = feedback.get("constraints", {})
        if constraints.get("tone"):
            memory.preference_memory["copy_tone"] = constraints["tone"]
        if constraints.get("style"):
            memory.preference_memory["poster_style"] = constraints["style"]
        if constraints.get("color"):
            memory.preference_memory["poster_color"] = constraints["color"]
        feedback_log = memory.preference_memory.setdefault("feedback_log", [])
        raw_feedback = constraints.get("raw_feedback")
        if raw_feedback:
            feedback_log.append(raw_feedback)

    @staticmethod
    def _to_agent_state(state: Dict[str, Any]) -> AgentState:
        """把图状态字典转换为结构化 AgentState。"""
        return AgentState(
            session_id=state["session_id"],
            request=state["request"],
            intent_type=state.get("intent_type", ""),
            entities=state.get("entities") or {},
            next_nodes=state.get("remaining_nodes") or [],
            query_result=state.get("query_result"),
            query_plan=state.get("query_plan"),
            insight=state.get("insight"),
            target_users=state.get("target_users") or [],
            ad_copy=state.get("ad_copy"),
            poster_spec=state.get("poster_spec"),
            generated_image=state.get("generated_image"),
            feedback=state.get("feedback"),
            parsed_message=state.get("parsed_message"),
            response_text=state.get("response_text", ""),
            error=state.get("error"),
            trace=state.get("trace") or [],
        )

    def _finalize(self, memory: ConversationMemory, state: AgentState) -> None:
        """更新会话记忆并持久化助手回复。"""
        if state.entities:
            memory.last_entities.update({key: value for key, value in state.entities.items() if value})
        if state.intent_type:
            memory.last_intent_type = state.intent_type
        if state.insight:
            memory.last_artifacts["insight"] = state.insight
        if state.target_users:
            memory.last_artifacts["target_users"] = state.target_users
        if state.ad_copy:
            memory.last_artifacts["ad_copy"] = state.ad_copy
            memory.pending_artifact = "ad_copy"
        if state.poster_spec:
            memory.last_artifacts["poster_spec"] = state.poster_spec
            memory.pending_artifact = "poster"
        if state.generated_image:
            memory.last_artifacts["generated_image"] = state.generated_image
            memory.pending_artifact = "poster"
        if state.feedback and state.feedback.get("is_approval"):
            memory.pending_artifact = None

        memory.history.append(ChatMessage(role="assistant", content=state.response_text))
        memory.history = memory.history[-20:]
        self.db.save_memory(memory)
        self.db.append_message(memory.session_id, "assistant", state.response_text)

    @staticmethod
    def _build_response(state: AgentState, memory: ConversationMemory) -> ChatResponse:
        """构建对外返回结构。"""
        return ChatResponse(
            session_id=state.session_id,
            reply=state.response_text,
            intent_type=state.intent_type,
            error=state.error,
            trace=state.trace,
            entities=state.entities,
            query_plan=MarketingWorkflow._public_query_plan(state.query_plan),
            insight=state.insight,
            target_users=state.target_users,
            ad_copy=state.ad_copy,
            poster_spec=state.poster_spec,
            generated_image=state.generated_image,
            parsed_message=state.parsed_message,
            memory={
                "pending_artifact": memory.pending_artifact,
                "last_entities": memory.last_entities,
                "preference_memory": memory.preference_memory,
            },
        )

    @staticmethod
    def _public_query_plan(query_plan: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """压缩 query_plan，减少响应噪音。"""
        if not query_plan:
            return None
        filters = query_plan.get("filters") or {}
        compact_filters = {key: value for key, value in filters.items() if value}
        result = {
            "query_goal": query_plan.get("query_goal"),
            "tables": query_plan.get("tables") or [],
            "filters": compact_filters,
            "behavior_scope": query_plan.get("behavior_scope") or [],
            "limit": query_plan.get("limit"),
            "sort_by": query_plan.get("sort_by"),
            "query_mode": query_plan.get("query_mode"),
        }
        if query_plan.get("sql_source"):
            result["sql_source"] = query_plan.get("sql_source")
        return result
