"""LangGraph 智能体记忆：AsyncSqliteSaver 进程级单例。

对话状态存在独立 SQLite 文件（backend/data/agent_memory.db），随 data 目录一起被备份功能覆盖。
thread_id 规则：chat-{session_id}，与 chat_sessions 表一一对应。
"""

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import settings

_saver: AsyncSqliteSaver | None = None


def thread_id(session_id: int) -> str:
    return f"chat-{session_id}"


async def init_checkpointer() -> AsyncSqliteSaver:
    """在 FastAPI lifespan 中调用一次；必须在事件循环内构造（内部绑定 loop）。"""
    global _saver
    import aiosqlite

    settings.AGENT_MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(settings.AGENT_MEMORY_DB.as_posix())
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    _saver = saver
    return saver


async def close_checkpointer() -> None:
    global _saver
    if _saver is not None:
        await _saver.conn.close()
        _saver = None


def get_checkpointer() -> AsyncSqliteSaver | None:
    return _saver


async def delete_thread(session_id: int) -> None:
    if _saver is not None:
        await _saver.adelete_thread(thread_id(session_id))
