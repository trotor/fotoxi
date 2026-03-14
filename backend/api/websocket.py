"""WebSocket endpoint for Fotoxi real-time progress updates."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time indexer progress updates.

    Accepts the connection, registers it in the app's ws_connections list,
    keeps the connection alive by reading messages, and cleans up on disconnect.
    """
    await websocket.accept()

    ws_connections: list = websocket.app.state.ws_connections
    ws_connections.append(websocket)

    try:
        while True:
            # Keep connection alive; clients can send any text to ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        try:
            ws_connections.remove(websocket)
        except ValueError:
            pass
