"""HUD WebSocket server — streams pipeline events to the HUD frontend.

The HUD (at hud/) connects via ws://localhost:7788 and renders live
transcript, tool calls, speaking state, and the idle/thinking lifecycle.

Public API:
- start_hud_server(): create the server, call once at pipeline startup
- broadcast(event_type, data=None): fan out a JSON event to all clients
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets

logging.getLogger("websockets").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)

_clients: set = set()
_server = None


async def _handler(ws) -> None:
    """Register a new client and keep the connection alive until close."""
    _clients.add(ws)
    try:
        await ws.send(json.dumps({"type": "connected"}))
        await ws.wait_closed()
    except Exception:
        pass
    finally:
        _clients.discard(ws)


async def broadcast(event_type: str, data: Any = None) -> None:
    """Fan out a JSON event to every connected HUD client."""
    if not _clients:
        return
    message = json.dumps({"type": event_type, "data": data})
    await asyncio.gather(
        *[client.send(message) for client in list(_clients)],
        return_exceptions=True,
    )


async def start_hud_server(host: str = "localhost", port: int = 7788) -> None:
    """Bind the HUD WebSocket server. Idempotent within a process."""
    global _server
    if _server is not None:
        return

    # Silence the websockets library completely — Electron/Chromium sends
    # plain HTTP health-check probes before upgrading to WebSocket, which
    # would otherwise flood stderr with 'InvalidMessage' tracebacks.
    for name in ("websockets", "websockets.server", "websockets.asyncio.server"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
        logging.getLogger(name).propagate = False

    _server = await websockets.serve(_handler, host, port, logger=None)
    logger.info("HUD WebSocket server started on ws://%s:%d", host, port)


def client_count() -> int:
    """Return the number of currently-connected HUD clients."""
    return len(_clients)
