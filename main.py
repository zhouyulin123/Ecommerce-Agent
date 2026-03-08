import argparse
import json
from typing import Any, Dict, List

import uvicorn

from app.api.routes import app
from app.config import load_settings
from app.workflow import MarketingWorkflow


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="AI Ecommerce Marketing Agent MVP")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="启动 FastAPI 服务")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    chat = subparsers.add_parser("chat", help="命令行单轮对话")
    chat.add_argument("--message", required=True)
    chat.add_argument("--session-id", default="")
    chat.add_argument("--json", action="store_true", help="输出精简 JSON")
    chat.add_argument("--json-full", action="store_true", help="输出完整 JSON")
    chat.add_argument("--pretty", action="store_true", help="输出可读性更高的调试文本")

    return parser


def _compact_query_plan(query_plan: Dict[str, Any]) -> Dict[str, Any]:
    """压缩 query_plan 字段，仅保留高价值信息。"""
    if not query_plan:
        return {}
    filters = query_plan.get("filters") or {}
    return {
        "query_goal": query_plan.get("query_goal"),
        "filters": {key: value for key, value in filters.items() if value},
        "behavior_scope": query_plan.get("behavior_scope") or [],
        "query_mode": query_plan.get("query_mode"),
        "sql_source": query_plan.get("sql_source"),
    }


def _compact_target_users(target_users: List[Dict[str, Any]]) -> Dict[str, Any]:
    """压缩目标人群输出，默认仅保留前 10 条关键字段。"""
    rows = target_users or []
    compact_rows = [
        {
            "user_name": row.get("user_name"),
            "address": row.get("address"),
            "buy_count": int(row.get("buy_count") or 0),
            "view_count": int(row.get("view_count") or 0),
        }
        for row in rows[:10]
    ]
    return {
        "count": len(rows),
        "top_users": compact_rows,
    }


def _compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """构建精简 JSON 输出，用于测试阶段快速查看。"""
    generated_image = payload.get("generated_image") or {}
    return {
        "session_id": payload.get("session_id"),
        "reply": payload.get("reply"),
        "intent_type": payload.get("intent_type"),
        "error": payload.get("error"),
        "trace": payload.get("trace") or [],
        "parsed_message": payload.get("parsed_message") or {},
        "entities": payload.get("entities") or {},
        "query_plan": _compact_query_plan(payload.get("query_plan") or {}),
        "target_users": _compact_target_users(payload.get("target_users") or []),
        "ad_copy": payload.get("ad_copy"),
        "poster_spec": payload.get("poster_spec"),
        "generated_image": {
            "url": generated_image.get("url"),
            "local_path": generated_image.get("local_path"),
            "file_name": generated_image.get("file_name"),
        }
        if generated_image
        else None,
        "memory": payload.get("memory") or {},
    }


def _format_pretty_response(response: Any) -> str:
    """把响应对象格式化为更直观的多行文本，便于人工验收。"""
    lines = [f"session_id: {response.session_id}"]

    if getattr(response, "parsed_message", None):
        parsed = response.parsed_message or {}
        parse_parts = []
        if parsed.get("normalized_message"):
            parse_parts.append(f"归一化={parsed['normalized_message']}")
        if parsed.get("intent_hint"):
            parse_parts.append(f"意图提示={parsed['intent_hint']}")
        parsed_entities = parsed.get("entities") or {}
        if parsed_entities:
            entity_text = ", ".join(f"{k}={v}" for k, v in parsed_entities.items() if v)
            if entity_text:
                parse_parts.append(f"解析实体={entity_text}")
        if parse_parts:
            lines.append(f"解析结果: {' | '.join(parse_parts)}")

    if response.intent_type:
        lines.append(f"意图: {response.intent_type}")
    if response.trace:
        lines.append(f"执行节点: {' -> '.join(response.trace)}")
    if response.entities:
        entity_parts = [f"{key}={value}" for key, value in response.entities.items() if value]
        if entity_parts:
            lines.append(f"识别实体: {', '.join(entity_parts)}")
    if response.query_plan:
        filters = response.query_plan.get("filters") or {}
        filter_parts = [f"{key}={value}" for key, value in filters.items() if value]
        tables = "、".join(response.query_plan.get("tables") or [])
        behaviors = "/".join(response.query_plan.get("behavior_scope") or [])
        plan_parts = []
        if response.query_plan.get("query_goal"):
            plan_parts.append(f"目标={response.query_plan['query_goal']}")
        if tables:
            plan_parts.append(f"表={tables}")
        if behaviors:
            plan_parts.append(f"行为={behaviors}")
        if filter_parts:
            plan_parts.append(f"条件={', '.join(filter_parts)}")
        if plan_parts:
            lines.append(f"查询计划: {' | '.join(plan_parts)}")

    lines.append("")
    lines.append(response.reply)
    return "\n".join(lines)


def main() -> None:
    """单轮对话或启动 API 服务。"""
    args = build_parser().parse_args()
    settings = load_settings()

    if args.command == "chat":
        workflow = MarketingWorkflow(settings)
        response = workflow.handle_message(args.message, session_id=args.session_id)
        dumper = getattr(response, "model_dump", None)
        payload = dumper() if dumper else response.dict()
        if args.json_full:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        elif args.json:
            print(json.dumps(_compact_payload(payload), ensure_ascii=False, indent=2, default=str))
        elif args.pretty:
            print(_format_pretty_response(response))
        else:
            print(f"session_id: {response.session_id}")
            print(response.reply)
        return

    host = args.host or settings.host
    port = args.port or settings.port
    uvicorn.run(app, host=host, port=port, reload=bool(getattr(args, "reload", False)))


if __name__ == "__main__":
    main()
