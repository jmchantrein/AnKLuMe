"""WebSocket endpoint for xterm.js terminal sessions.

Relays I/O between xterm.js (browser) and a PTY session managed by
PtyManager. Supports text I/O and JSON control messages (resize).

Security: connections are restricted to localhost origins only.
Session IDs are validated to prevent path injection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from scripts.web.pty_manager import PtyManager

logger = logging.getLogger(__name__)

router = APIRouter()
manager = PtyManager(max_sessions=4, idle_timeout=1800)

# Allowed origins — only localhost connections.
_ALLOWED_ORIGINS = re.compile(
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
)

# Session IDs: alphanumeric + hyphen, max 64 chars.
_VALID_SESSION_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@router.websocket("/ws/terminal/{session_id}")
async def terminal_ws(ws: WebSocket, session_id: str) -> None:
    """Bidirectional WebSocket relay between xterm.js and a PTY."""
    # Validate session ID format
    if not _VALID_SESSION_ID.match(session_id):
        await ws.close(code=1008, reason="Invalid session ID")
        return

    # Origin check — reject non-localhost connections
    origin = ws.headers.get("origin", "")
    if origin and not _ALLOWED_ORIGINS.match(origin):
        await ws.close(code=1008, reason="Forbidden origin")
        return

    await ws.accept()
    try:
        session = manager.create(session_id)
    except RuntimeError as e:
        await ws.send_text(f"\r\nError: {e}\r\n")
        await ws.close()
        return

    read_task = asyncio.create_task(
        manager.read_loop(session_id, lambda data: ws.send_bytes(data)),
    )
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "bytes" in msg and msg["bytes"]:
                session.write(msg["bytes"])
            elif "text" in msg and msg["text"]:
                text = msg["text"]
                try:
                    ctrl = json.loads(text)
                    if ctrl.get("type") == "resize":
                        session.resize(
                            ctrl.get("cols", 80), ctrl.get("rows", 24),
                        )
                        continue
                except (json.JSONDecodeError, KeyError):
                    pass
                session.write(text.encode())
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        read_task.cancel()
        manager.close(session_id)


def get_manager() -> PtyManager:
    """Return the global PTY manager (for shutdown hooks)."""
    return manager
