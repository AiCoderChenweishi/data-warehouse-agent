"""会话状态存储 (内存 dict).

按 session_id 存各阶段产出. 简单内存版, 重启即清 (MVP).
"""
from __future__ import annotations

import time
from typing import Any, Optional


class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.stages_completed: list[int] = []
        self.data: dict[str, Any] = {}


_STORE: dict[str, SessionData] = {}


def get_or_create(session_id: str) -> SessionData:
    """获取或创建会话."""
    if session_id not in _STORE:
        _STORE[session_id] = SessionData(session_id)
    return _STORE[session_id]


def get(session_id: str) -> Optional[SessionData]:
    return _STORE.get(session_id)


def mark_complete(session_id: str, stage: int) -> None:
    s = get_or_create(session_id)
    if stage not in s.stages_completed:
        s.stages_completed.append(stage)
        s.stages_completed.sort()


def all_sessions() -> list[str]:
    return list(_STORE.keys())
