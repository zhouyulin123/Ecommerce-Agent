from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    """Return a compact UTC timestamp for chat history records."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str = Field(default_factory=now_iso)


class ConversationMemory(BaseModel):
    session_id: str
    history: List[ChatMessage] = Field(default_factory=list)
    preference_memory: Dict[str, Any] = Field(default_factory=dict)
    last_entities: Dict[str, Any] = Field(default_factory=dict)
    last_artifacts: Dict[str, Any] = Field(default_factory=dict)
    pending_artifact: Optional[str] = None
    last_intent_type: Optional[str] = None


class AgentState(BaseModel):
    session_id: str
    request: str
    intent_type: str = ""
    entities: Dict[str, Any] = Field(default_factory=dict)
    next_nodes: List[str] = Field(default_factory=list)
    query_result: Optional[Dict[str, Any]] = None
    query_plan: Optional[Dict[str, Any]] = None
    insight: Optional[Dict[str, Any]] = None
    target_users: List[Dict[str, Any]] = Field(default_factory=list)
    ad_copy: Optional[Dict[str, Any]] = None
    poster_spec: Optional[Dict[str, Any]] = None
    generated_image: Optional[Dict[str, Any]] = None
    feedback: Optional[Dict[str, Any]] = None
    parsed_message: Optional[Dict[str, Any]] = None
    response_text: str = ""
    error: Optional[str] = None
    trace: List[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    debug: bool = False


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent_type: str
    error: Optional[str] = None
    trace: List[str] = Field(default_factory=list)
    entities: Dict[str, Any] = Field(default_factory=dict)
    query_plan: Optional[Dict[str, Any]] = None
    insight: Optional[Dict[str, Any]] = None
    target_users: List[Dict[str, Any]] = Field(default_factory=list)
    ad_copy: Optional[Dict[str, Any]] = None
    poster_spec: Optional[Dict[str, Any]] = None
    generated_image: Optional[Dict[str, Any]] = None
    parsed_message: Optional[Dict[str, Any]] = None
    memory: Dict[str, Any] = Field(default_factory=dict)
