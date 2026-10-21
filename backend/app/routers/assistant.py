"""AI 助手：台账问答（LangGraph 智能体 + SqliteSaver 多轮记忆）、会话管理、可视化报告、异常预警。"""

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.deps import require_manager
from app.models import ChatSession, Report, User
from app.services.agent import build_agent
from app.services.agent_memory import delete_thread, get_checkpointer, thread_id
from app.services.insights import compute_anomalies
from app.services.llm import get_effective_llm_config
from app.services.report_builder import create_report

router = APIRouter(prefix="/api/assistant", tags=["AI 助手"])


@router.get("/anomalies")
def anomalies(days: int = 14, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    alerts = compute_anomalies(db, days)
    return {"count": len(alerts), "alerts": alerts}


# ──────────────────────────── 会话管理（多轮记忆） ────────────────────────────

def _own_session(db: Session, session_id: int, user: User) -> ChatSession:
    row = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return row


def _session_out(s: ChatSession) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(require_manager)):
    rows = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(100)
        .all()
    )
    return [_session_out(s) for s in rows]


@router.post("/sessions")
def create_session(db: Session = Depends(get_db), user: User = Depends(require_manager)):
    row = ChatSession(user_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _session_out(row)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    row = _own_session(db, session_id, user)
    db.delete(row)
    db.commit()
    await delete_thread(session_id)
    return {"message": "会话已删除"}


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    """回放会话历史（从 checkpointer 读，含工具调用行）。"""
    _own_session(db, session_id, user)
    saver = get_checkpointer()
    if saver is None:
        return {"messages": []}

    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    reader = create_react_agent(ChatOpenAI(model="reader", api_key="unused"), [], checkpointer=saver)
    state = await reader.aget_state({"configurable": {"thread_id": thread_id(session_id)}})
    result = []
    for m in (state.values or {}).get("messages", []):
        if isinstance(m, HumanMessage):
            result.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage):
            if m.tool_calls:
                names = "、".join(tc.get("name", "工具") for tc in m.tool_calls)
                result.append({"role": "assistant", "tool": names})
            elif m.content:
                result.append({"role": "assistant", "content": str(m.content)})
    return {"messages": result}


# ──────────────────────────── 台账问答（流式，带记忆） ────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: int | None = None  # 不传则自动新建会话


@router.post("/chat")
async def chat(body: ChatRequest, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    cfg = get_effective_llm_config(db)
    if not cfg:
        raise HTTPException(status_code=400, detail="请先在「系统设置」中配置大模型 API，再使用 AI 问答")
    saver = get_checkpointer()
    if saver is None:
        raise HTTPException(status_code=503, detail="记忆服务未初始化，请重启后端")

    # 会话：自动新建或校验属主；首条消息设置标题
    if body.session_id is None:
        session = ChatSession(user_id=user.id, title=body.message[:20])
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session = _own_session(db, body.session_id, user)
        if session.title in ("", "新对话"):
            session.title = body.message[:20]
            db.commit()
            db.refresh(session)
    session_id, session_title = session.id, session.title
    db.close()

    config = {"configurable": {"thread_id": thread_id(session_id)}}

    async def event_stream():
        def sse(payload: dict) -> str:
            return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

        yield sse({"session_id": session_id, "title": session_title})

        # 智能体使用独立会话：流式响应在请求依赖关闭后仍继续执行
        session_db = SessionLocal()
        try:
            graph = build_agent(cfg, session_db, checkpointer=saver)
            async for ev in graph.astream_events(
                {"messages": [{"role": "user", "content": body.message}]},
                config=config,
                version="v2",
            ):
                kind = ev["event"]
                if kind == "on_chat_model_stream":
                    content = ev["data"]["chunk"].content
                    if isinstance(content, list):  # 多模态内容片段
                        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                    if content:
                        yield sse({"delta": content})
                elif kind == "on_tool_start":
                    yield sse({"tool": ev.get("name", "工具")})
            yield "data: [DONE]\n\n"
        except Exception as e:  # noqa: BLE001 - 把执行失败流式反馈给前端
            yield sse({"delta": f"\n\n[智能体执行失败：{e}]"})
            yield "data: [DONE]\n\n"
        finally:
            session_db.close()
            touch = SessionLocal()
            try:
                row = touch.query(ChatSession).filter(ChatSession.id == session_id).first()
                if row:
                    row.updated_at = datetime.now()
                    touch.commit()
            finally:
                touch.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────── 可视化报告（周报 / 月报） ────────────────────────────

class ReportRequest(BaseModel):
    report_type: str = Field(pattern="^(weekly|monthly)$")
    anchor_date: str | None = None  # YYYY-MM-DD，默认今天


@router.post("/report")
def create_report_api(
    body: ReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    cfg = get_effective_llm_config(db)
    if not cfg:
        raise HTTPException(status_code=400, detail="请先在「系统设置」中配置大模型 API，再生成 AI 报告")
    anchor = date.today()
    if body.anchor_date:
        try:
            anchor = date.fromisoformat(body.anchor_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    try:
        return create_report(cfg, db, user, body.report_type, anchor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _report_out(r: Report, with_content: bool = True) -> dict:
    out = {
        "id": r.id,
        "report_type": r.report_type,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "creator_name": r.creator_name,
        "created_at": r.created_at,
    }
    if with_content:
        out["content"] = r.content
        if r.charts:
            try:
                out["charts"] = json.loads(r.charts)
            except (ValueError, TypeError):
                pass
    return out


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    rows = db.query(Report).order_by(Report.id.desc()).limit(50).all()
    return [_report_out(r, with_content=False) for r in rows]


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    return _report_out(r)


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    r = db.query(Report).filter(Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    db.delete(r)
    db.commit()
    return {"message": "已删除"}
