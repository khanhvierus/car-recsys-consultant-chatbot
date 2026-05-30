"""Conversation memory — persists turns to gold.chat_messages and, instead of
hard-truncating at 10 messages, summarizes older turns so long conversations
keep their context.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import CHATBOT_CONFIG

log = logging.getLogger(__name__)


class ConversationMemory:
    def __init__(self, db_engine: Engine, llm: Any):
        self.db = db_engine
        self.llm = llm
        self.cfg = CHATBOT_CONFIG

    # ---- load -------------------------------------------------------------

    def load_turns(self, session_id: str) -> list[dict[str, Any]]:
        """All persisted turns for a session, oldest first."""
        try:
            with self.db.connect() as con:
                rows = con.execute(
                    text("""
                        SELECT role, content, created_at
                        FROM gold.chat_messages
                        WHERE session_id = :sid::uuid
                        ORDER BY created_at ASC, id ASC
                    """),
                    {"sid": session_id},
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("load_turns failed for %s: %s", session_id, exc)
            return []
        return [{"role": r[0], "content": r[1]} for r in rows]

    def build_context(self, session_id: str) -> list[BaseMessage]:
        """LangChain message list for the prompt. Recent turns verbatim; older
        turns collapsed into one summary system-ish message when the history
        grows past `summary_trigger_turns`."""
        turns = self.load_turns(session_id)
        if not turns:
            return []

        recent_cut = self.cfg.max_history_turns
        if len(turns) <= self.cfg.summary_trigger_turns:
            return self._to_messages(turns)

        older, recent = turns[:-recent_cut], turns[-recent_cut:]
        summary = self._summarize(older)
        messages: list[BaseMessage] = []
        if summary:
            messages.append(HumanMessage(
                content=f"[Earlier conversation summary]: {summary}"))
        messages.extend(self._to_messages(recent))
        return messages

    @staticmethod
    def _to_messages(turns: list[dict[str, Any]]) -> list[BaseMessage]:
        out: list[BaseMessage] = []
        for t in turns:
            if t["role"] == "user":
                out.append(HumanMessage(content=t["content"]))
            elif t["role"] == "assistant":
                out.append(AIMessage(content=t["content"]))
        return out

    def _summarize(self, turns: list[dict[str, Any]]) -> str:
        if not turns:
            return ""
        transcript = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
        try:
            from langchain_core.messages import SystemMessage
            resp = self.llm.invoke([
                SystemMessage(content=(
                    "Summarize this car-shopping conversation in 2-3 sentences, "
                    "keeping the user's stated preferences (budget, brand, body "
                    "type, must-have features). Output only the summary.")),
                HumanMessage(content=transcript),
            ])
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as exc:  # noqa: BLE001
            log.warning("history summarization failed: %s", exc)
            return ""

    # ---- persist ----------------------------------------------------------

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        vehicles: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        try:
            with self.db.begin() as con:
                con.execute(
                    text("""
                        INSERT INTO gold.chat_messages
                            (session_id, role, content, vehicles)
                        VALUES (:sid::uuid, :role, :content, :vehicles)
                    """),
                    {
                        "sid": session_id,
                        "role": role,
                        "content": content,
                        "vehicles": json.dumps(vehicles) if vehicles else None,
                    },
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("append message failed for %s: %s", session_id, exc)

    def ensure_session(
        self, session_id: Optional[str], user_id: Optional[str]
    ) -> str:
        """Return an existing session id or create a new chat_sessions row."""
        try:
            with self.db.begin() as con:
                if session_id:
                    row = con.execute(
                        text("SELECT id FROM gold.chat_sessions WHERE id = :sid::uuid"),
                        {"sid": session_id},
                    ).fetchone()
                    if row:
                        return str(row[0])
                row = con.execute(
                    text("""
                        INSERT INTO gold.chat_sessions (user_id)
                        VALUES (:uid)
                        RETURNING id
                    """),
                    {"uid": user_id},
                ).fetchone()
                return str(row[0])
        except Exception as exc:  # noqa: BLE001
            log.error("ensure_session failed: %s", exc)
            raise
