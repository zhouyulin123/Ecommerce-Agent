from fastapi import FastAPI, HTTPException

from app.config import load_settings
from app.state import ChatRequest, ChatResponse
from app.workflow import MarketingWorkflow


settings = load_settings()
workflow = MarketingWorkflow(settings)
app = FastAPI(title="AI Ecommerce Marketing Agent", version="0.1.0")


@app.get("/health")
def health() -> dict:
    """健康检查：返回服务状态和模型开关信息。"""
    return {
        "status": "ok",
        "llm_enabled": workflow.llm.enabled,
        "image_enabled": workflow.llm.image_enabled,
        "image_model": workflow.settings.openai_image_model,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """聊天接口：接收用户消息并返回工作流结果。"""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    return workflow.handle_message(payload.message.strip(), session_id=payload.session_id or "")


@app.get("/api/sessions/{session_id}")
def session_history(session_id: str) -> dict:
    """会话查询接口：返回该 session 的记忆状态和消息历史。"""
    memory = workflow.db.load_memory(session_id)
    history = workflow.db.get_history(session_id)
    dumper = getattr(memory, "model_dump", None)
    return {
        "session_id": session_id,
        "memory": dumper() if dumper else memory.dict(),
        "history": history,
    }
