from typing import Dict, Any, Optional
import uuid
import time

SESSION_TTL_SECONDS = 3600


class TourSessionStore:
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _gc(self) -> None:
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.get("updated_at", now) > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self._sessions.pop(sid, None)

    def create_session(self, payload: Dict[str, Any]) -> str:
        self._gc()
        session_id = f"tour_{uuid.uuid4().hex[:12]}"
        now = time.time()
        self._sessions[session_id] = {
            "session_id": session_id,
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "current_step_index": 0,
            "plan": None,
            "history": [],
            "config": payload,
            # ✅ 新增：自由问答历史
            "chat_history": [],
            # ✅ 新增：当前观测上下文快照
            "observation_context": {},
        }
        return session_id

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def update(self, session_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.update(patch)
        session["updated_at"] = time.time()
        return session

    def stop(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if session:
            session["status"] = "stopped"
            session["updated_at"] = time.time()
        return session


tour_store = TourSessionStore()