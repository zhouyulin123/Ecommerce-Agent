from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.infra.config import load_settings
from app.runtime.state import ChatRequest, ChatResponse
from app.runtime.workflow import MarketingWorkflow


settings = load_settings()
workflow = MarketingWorkflow(settings)
app = FastAPI(title="电商营销多智能体系统", version="0.1.0")

frontend_dir = Path(__file__).resolve().parents[2] / "Visual page"
if frontend_dir.exists():
    app.mount("/workbench", StaticFiles(directory=str(frontend_dir), html=True), name="workbench")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/workbench/")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": workflow.llm.enabled,
        "image_enabled": workflow.llm.image_enabled,
        "text_model": workflow.settings.openai_model,
        "image_model": workflow.settings.openai_image_model,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    return workflow.handle_message(payload.message.strip(), session_id=payload.session_id or "")


@app.get("/api/sessions/{session_id}")
def session_history(session_id: str) -> dict:
    memory = workflow.db.load_memory(session_id)
    history = workflow.db.get_history(session_id)
    dumper = getattr(memory, "model_dump", None)
    return {"session_id": session_id, "memory": dumper() if dumper else memory.dict(), "history": history}


@app.get("/api/sessions")
def session_list(limit: int = 20) -> dict:
    return {"sessions": workflow.db.list_sessions(limit=limit)}
