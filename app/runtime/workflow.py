import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.creative import CreativeAgent, PosterPromptNode
from app.agents.data import DataAgent, UserInsightNode
from app.agents.executor import Executor
from app.agents.planner import PlannerAgent, QueryPlannerAgent
from app.agents.response import ResponseAgent
from app.agents.supervisor import (
    FeedbackParserAgent,
    INTENT_AUDIENCE_QUERY,
    INTENT_COMBINED,
    INTENT_POSTER,
    MessageParserAgent,
    RouterAgent,
    SupervisorAgent,
)
from app.agents.writing import CopywritingNode, WritingAgent
from app.constants import EXECUTOR_NODE, PLANNER_AGENT, RESPONSE_AGENT, SUPERVISOR_AGENT
from app.infra.config import Settings
from app.infra.database import DatabaseManager
from app.infra.llm import LLMClient
from app.runtime.state import AgentState, ChatMessage, ChatResponse, ConversationMemory, ToolCallRecord
from app.tools.creative import CreativeToolbelt, ImageGenerationTool
from app.tools.data import AudienceSelectionTool, DataToolbelt, SQLQueryTool


class WorkflowGraphState(TypedDict, total=False):
    session_id: str
    request: str
    memory: ConversationMemory
    supervisor_mode: str
    feedback: Dict[str, Any]
    parsed_message: Dict[str, Any]
    intent_type: str
    entities: Dict[str, Any]
    task_queue: List[str]
    execution_plan: Dict[str, Any]
    active_agent: str
    query_result: Dict[str, Any]
    query_plan: Dict[str, Any]
    insight: Dict[str, Any]
    target_users: List[Dict[str, Any]]
    ad_copy: Dict[str, Any]
    poster_spec: Dict[str, Any]
    generated_image: Dict[str, Any]
    tool_calls: List[ToolCallRecord]
    execution_steps: List[Dict[str, Any]]
    response_text: str
    error: str
    trace: List[str]


class MarketingWorkflow:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = DatabaseManager(settings)
        self.db.bootstrap()
        self.llm = LLMClient(settings)

        self.supervisor = SupervisorAgent(
            FeedbackParserAgent(self.llm),
            MessageParserAgent(self.llm),
            RouterAgent(self.db, self.llm),
        )
        self.planner = PlannerAgent(QueryPlannerAgent(self.db, self.llm))
        self.executor = Executor()
        self.data_agent = DataAgent(self.llm, DataToolbelt(SQLQueryTool(self.db), AudienceSelectionTool(self.db)), UserInsightNode())
        self.writing_agent = WritingAgent(CopywritingNode(self.llm))
        self.creative_agent = CreativeAgent(self.llm, PosterPromptNode(self.llm), CreativeToolbelt(ImageGenerationTool(self.llm)))
        self.response_agent = ResponseAgent(self.llm)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(WorkflowGraphState)
        graph.add_node("supervisor", self._supervisor_step)
        graph.add_node("planner", self._planner_step)
        graph.add_node("executor", self._executor_step)
        graph.add_node("data_agent", self._data_agent_step)
        graph.add_node("writing_agent", self._writing_agent_step)
        graph.add_node("creative_agent", self._creative_agent_step)
        graph.add_node("response", self._response_step)
        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges("supervisor", self._after_supervisor, {"approval": "response", "revision": "executor", "plan": "planner"})
        graph.add_edge("planner", "executor")
        graph.add_conditional_edges("executor", self._executor_route, {"data_agent": "data_agent", "writing_agent": "writing_agent", "creative_agent": "creative_agent", "response": "response"})
        graph.add_edge("data_agent", "executor")
        graph.add_edge("writing_agent", "executor")
        graph.add_edge("creative_agent", "executor")
        graph.add_edge("response", END)
        return graph.compile()

    def handle_message(self, message: str, session_id: str = "") -> ChatResponse:
        active_session_id = session_id or str(uuid.uuid4())
        memory = self.db.load_memory(active_session_id)
        self.db.append_message(active_session_id, "user", message)
        memory.history.append(ChatMessage(role="user", content=message))
        initial_state: WorkflowGraphState = {"session_id": active_session_id, "request": message, "memory": memory, "entities": {}, "task_queue": [], "tool_calls": [], "execution_steps": [], "trace": []}
        result = self.graph.invoke(initial_state)
        agent_state = self._to_agent_state(result)
        self._finalize(memory, agent_state)
        return self._build_response(agent_state, memory)

    def _supervisor_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        decision = self.supervisor.inspect(state["request"], state["memory"])
        feedback = decision.get("feedback") or {}
        if feedback.get("is_revision"):
            self._merge_preferences(state["memory"], feedback)
        update: Dict[str, Any] = {
            "supervisor_mode": decision["mode"],
            "feedback": feedback,
            "parsed_message": decision.get("parsed_message") or {},
            "intent_type": decision.get("intent_type", ""),
            "entities": decision.get("entities") or {},
            "task_queue": decision.get("requested_tasks") or [],
            "active_agent": SUPERVISOR_AGENT,
            "trace": self._append_trace(state, SUPERVISOR_AGENT),
        }
        if decision["mode"] == "revision" and update["task_queue"]:
            update["execution_plan"] = {
                "intent_type": update.get("intent_type", ""),
                "tasks": list(update.get("task_queue") or []),
                "query_goal": "revision",
                "query_mode": "revision",
            }
        if decision["mode"] == "revision" and not update["task_queue"]:
            update["error"] = "当前反馈没有对应到可修改的海报或文案结果。"
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "supervisor",
                "mode": decision["mode"],
                "intent_type": update.get("intent_type", ""),
                "requested_tasks": update.get("task_queue") or [],
                "entities": self._compact_entities(update.get("entities") or {}),
                "feedback": self._compact_feedback(feedback),
            },
        )
        return update

    @staticmethod
    def _after_supervisor(state: WorkflowGraphState) -> str:
        mode = state.get("supervisor_mode", "plan")
        if mode == "approval":
            return "approval"
        if mode == "revision":
            return "revision"
        return "plan"

    def _planner_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        plan = self.planner.build_plan(state["request"], state.get("intent_type", ""), state.get("entities") or {}, state["memory"], state.get("task_queue") or [])
        update = {"execution_plan": plan["execution_plan"], "query_plan": plan.get("query_plan") or {}, "task_queue": plan["task_queue"], "active_agent": PLANNER_AGENT, "trace": self._append_trace(state, PLANNER_AGENT)}
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "planner",
                "tasks": plan["task_queue"],
                "execution_plan": self._compact_execution_plan(plan["execution_plan"]),
                "query_plan": self._public_query_plan(plan.get("query_plan") or {}),
            },
        )
        return update

    def _executor_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        next_agent = self.executor.next_agent(state.get("task_queue") or [])
        current_task = (state.get("task_queue") or [""])[0]
        update = {"active_agent": next_agent, "trace": self._append_trace(state, EXECUTOR_NODE)}
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "executor",
                "next_agent": next_agent,
                "current_task": current_task,
                "remaining_tasks": list(state.get("task_queue") or []),
                "dispatch_reason": self._dispatch_reason(current_task, next_agent),
            },
        )
        return update

    def _executor_route(self, state: WorkflowGraphState) -> str:
        if state.get("error") or not state.get("task_queue"):
            return "response"
        return self.executor.route_map().get(self.executor.next_agent(state.get("task_queue") or []), "response")

    def _data_agent_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        update = self.data_agent.run(state)
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "data_agent",
                "task": ((state.get("task_queue") or [""])[0]),
                "selection_reason": update.get("selection_reason"),
                "tool_call": self._tool_call_summary((update.get("tool_calls") or [])[-1] if update.get("tool_calls") else None),
                "query_result": self._compact_query_result(update.get("query_result")),
                "insight": self._compact_insight(update.get("insight")),
                "target_users": self._compact_target_users(update.get("target_users") or []),
                "error": update.get("error"),
            },
        )
        return update

    def _writing_agent_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        update = self.writing_agent.run(state)
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "writing_agent",
                "task": ((state.get("task_queue") or [""])[0]),
                "ad_copy": self._compact_ad_copy(update.get("ad_copy")),
                "entities": self._compact_entities(update.get("entities") or {}),
                "error": update.get("error"),
            },
        )
        return update

    def _creative_agent_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        update = self.creative_agent.run(state)
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "creative_agent",
                "task": ((state.get("task_queue") or [""])[0]),
                "selection_reason": update.get("selection_reason"),
                "tool_call": self._tool_call_summary((update.get("tool_calls") or [])[-1] if update.get("tool_calls") else None),
                "poster_spec": self._compact_poster_spec(update.get("poster_spec")),
                "generated_image": self._compact_generated_image(update.get("generated_image")),
                "error": update.get("error"),
            },
        )
        return update

    def _response_step(self, state: WorkflowGraphState) -> Dict[str, Any]:
        intent_type = state.get("intent_type", "")
        error = state.get("error")
        if intent_type == INTENT_AUDIENCE_QUERY and not state.get("target_users") and not error:
            error = "按当前条件没有找到可直接推送的用户。"
        if intent_type == INTENT_POSTER and not state.get("poster_spec") and not error:
            error = "海报提示词生成失败。"
        if intent_type == INTENT_COMBINED and not any([state.get("target_users"), state.get("ad_copy"), state.get("poster_spec"), state.get("generated_image")]) and not error:
            error = "组合任务没有产出可用结果。"
        response_state = dict(state)
        if error:
            response_state["error"] = error
        response_text = self.response_agent.compose(self._to_agent_state(response_state), state["memory"])
        update = {"active_agent": RESPONSE_AGENT, "error": error, "response_text": response_text, "trace": self._append_trace(state, RESPONSE_AGENT)}
        update["execution_steps"] = self._append_execution_step(
            state,
            {
                "stage": "response",
                "reply_preview": response_text[:160],
                "error": error,
            },
        )
        return update

    @staticmethod
    def _append_trace(state: WorkflowGraphState, *names: str) -> List[str]:
        trace = list(state.get("trace") or [])
        trace.extend(names)
        return trace

    @staticmethod
    def _merge_preferences(memory: ConversationMemory, feedback: Dict[str, Any]) -> None:
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
        return AgentState(
            session_id=state["session_id"],
            request=state["request"],
            intent_type=state.get("intent_type", ""),
            entities=state.get("entities") or {},
            task_queue=state.get("task_queue") or [],
            execution_plan=state.get("execution_plan"),
            active_agent=state.get("active_agent", ""),
            query_result=state.get("query_result"),
            query_plan=state.get("query_plan"),
            insight=state.get("insight"),
            target_users=state.get("target_users") or [],
            ad_copy=state.get("ad_copy"),
            poster_spec=state.get("poster_spec"),
            generated_image=state.get("generated_image"),
            feedback=state.get("feedback"),
            parsed_message=state.get("parsed_message"),
            tool_calls=state.get("tool_calls") or [],
            execution_steps=state.get("execution_steps") or [],
            response_text=state.get("response_text", ""),
            error=state.get("error"),
            trace=state.get("trace") or [],
        )

    def _finalize(self, memory: ConversationMemory, state: AgentState) -> None:
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
        return ChatResponse(
            session_id=state.session_id,
            reply=state.response_text,
            intent_type=state.intent_type,
            error=state.error,
            trace=state.trace,
            entities=state.entities,
            plan=state.execution_plan,
            query_plan=MarketingWorkflow._public_query_plan(state.query_plan),
            insight=state.insight,
            target_users=state.target_users,
            ad_copy=state.ad_copy,
            poster_spec=state.poster_spec,
            generated_image=state.generated_image,
            parsed_message=state.parsed_message,
            tool_calls=[MarketingWorkflow._serialize_tool_call(item) for item in state.tool_calls],
            execution_steps=state.execution_steps,
            memory={"pending_artifact": memory.pending_artifact, "last_entities": memory.last_entities, "preference_memory": memory.preference_memory},
        )

    @staticmethod
    def _serialize_tool_call(record: ToolCallRecord) -> Dict[str, Any]:
        dumper = getattr(record, "model_dump", None)
        return dumper() if dumper else record.dict()

    @staticmethod
    def _append_execution_step(state: WorkflowGraphState, step: Dict[str, Any]) -> List[Dict[str, Any]]:
        steps = list(state.get("execution_steps") or [])
        steps.append(step)
        return steps

    @staticmethod
    def _compact_entities(entities: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in entities.items() if value}

    @staticmethod
    def _compact_feedback(feedback: Dict[str, Any]) -> Dict[str, Any]:
        if not feedback:
            return {}
        return {
            "is_revision": bool(feedback.get("is_revision")),
            "is_approval": bool(feedback.get("is_approval")),
            "target_artifact": feedback.get("target_artifact"),
            "constraints": {key: value for key, value in (feedback.get("constraints") or {}).items() if value},
        }

    @staticmethod
    def _compact_execution_plan(execution_plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not execution_plan:
            return {}
        return {
            "intent_type": execution_plan.get("intent_type"),
            "tasks": execution_plan.get("tasks") or [],
            "query_goal": execution_plan.get("query_goal"),
            "query_mode": execution_plan.get("query_mode"),
        }

    @staticmethod
    def _compact_query_result(query_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not query_result:
            return None
        user_info = query_result.get("user_info") or {}
        return {
            "user_name": user_info.get("user_name"),
            "address": user_info.get("address"),
            "recent_views_count": len(query_result.get("recent_views") or []),
            "recent_buys_count": len(query_result.get("recent_buys") or []),
        }

    @staticmethod
    def _compact_insight(insight: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not insight:
            return None
        return {
            "summary": insight.get("summary"),
            "top_interest": insight.get("top_interest"),
            "purchase_power": insight.get("purchase_power"),
        }

    @staticmethod
    def _compact_target_users(target_users: List[Dict[str, Any]]) -> Dict[str, Any]:
        rows = target_users or []
        return {
            "count": len(rows),
            "sample": [
                {
                    "user_name": row.get("user_name"),
                    "address": row.get("address"),
                    "buy_count": row.get("buy_count"),
                    "view_count": row.get("view_count"),
                }
                for row in rows[:5]
            ],
        }

    @staticmethod
    def _compact_ad_copy(ad_copy: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not ad_copy:
            return None
        return {
            "title": ad_copy.get("title"),
            "subtitle": ad_copy.get("subtitle"),
            "cta": ad_copy.get("cta"),
        }

    @staticmethod
    def _compact_poster_spec(poster_spec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not poster_spec:
            return None
        return {
            "headline": poster_spec.get("headline"),
            "color_palette": poster_spec.get("color_palette"),
            "poster_prompt": (poster_spec.get("poster_prompt") or "")[:120],
        }

    @staticmethod
    def _compact_generated_image(generated_image: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not generated_image:
            return None
        return {
            "url": generated_image.get("url"),
            "local_path": generated_image.get("local_path"),
            "file_name": generated_image.get("file_name"),
        }

    @staticmethod
    def _tool_call_summary(record: Optional[ToolCallRecord]) -> Optional[Dict[str, Any]]:
        if not record:
            return None
        return {
            "tool_name": record.tool_name,
            "status": record.status,
            "error": record.error,
        }

    @staticmethod
    def _dispatch_reason(task: str, next_agent: str) -> str:
        if not task:
            return "当前没有待执行任务，流程准备收尾。"
        mapping = {
            "analyze_user": "当前任务需要先查询单用户行为与洞察。",
            "select_audience": "当前任务需要先筛选目标人群。",
            "write_copy": "当前任务需要生成或重写文案。",
            "prepare_poster": "当前任务需要先生成海报方案。",
            "generate_image": "当前任务需要把海报方案转换成图片。",
        }
        task_reason = mapping.get(task, "当前任务需要继续执行。")
        return f"{task_reason} 因此派发给 {next_agent}。"

    @staticmethod
    def _public_query_plan(query_plan: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not query_plan:
            return None
        filters = query_plan.get("filters") or {}
        compact_filters = {key: value for key, value in filters.items() if value}
        result = {"query_goal": query_plan.get("query_goal"), "tables": query_plan.get("tables") or [], "filters": compact_filters, "behavior_scope": query_plan.get("behavior_scope") or [], "limit": query_plan.get("limit"), "sort_by": query_plan.get("sort_by"), "query_mode": query_plan.get("query_mode")}
        if query_plan.get("sql_source"):
            result["sql_source"] = query_plan.get("sql_source")
        return result
