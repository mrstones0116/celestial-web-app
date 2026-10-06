import time
import uuid
from typing import Dict, Any, Optional, List

SESSION_TTL = 7200   # 2 小时


class AgentSessionStore:
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _gc(self):
        now = time.time()
        for sid in [k for k, v in self._sessions.items()
                    if now - v["updated_at"] > SESSION_TTL]:
            self._sessions.pop(sid, None)

    def create(self) -> str:
        self._gc()
        sid = f"agent_{uuid.uuid4().hex[:12]}"
        now = time.time()
        self._sessions[sid] = {
            "session_id": sid,
            "messages": [],          # OpenAI 格式的对话历史
            "created_at": now,
            "updated_at": now,
        }
        return sid

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(sid)

    def append_messages(self, sid: str, msgs: List[Dict[str, Any]]):
        s = self._sessions.get(sid)
        if not s:
            return
        s["messages"].extend(msgs)
        # 只保留最近 20 条，防止 token 爆炸
        s["messages"] = s["messages"][-20:]
        s["updated_at"] = time.time()

    def clear(self, sid: str):
        if sid in self._sessions:
            self._sessions[sid]["messages"] = []
            self._sessions[sid]["updated_at"] = time.time()


agent_store = AgentSessionStore()