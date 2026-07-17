"""
A plain in-memory dict of websocket connections only works if there's
exactly one backend process. The moment you run more than one uvicorn
worker (or more than one container) — which any real deployment will —
a visitor connected to worker A and an agent connected to worker B would
never see each other's messages. This manager broadcasts through Redis
pub/sub instead, so it's correct regardless of how many backend processes
are running.
"""
import asyncio
import json
import uuid
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import get_settings

settings = get_settings()


class WorkspaceBroadcaster:
    def __init__(self) -> None:
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self._local_sockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._listener_tasks: dict[str, asyncio.Task] = {}

    def _channel(self, workspace_id: uuid.UUID) -> str:
        return f"workspace:{workspace_id}:events"

    async def connect(self, workspace_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        channel = self._channel(workspace_id)
        self._local_sockets[channel].add(websocket)
        if channel not in self._listener_tasks:
            self._listener_tasks[channel] = asyncio.create_task(self._listen(channel))

    async def disconnect(self, workspace_id: uuid.UUID, websocket: WebSocket) -> None:
        channel = self._channel(workspace_id)
        self._local_sockets[channel].discard(websocket)
        if not self._local_sockets[channel]:
            task = self._listener_tasks.pop(channel, None)
            if task:
                task.cancel()
            del self._local_sockets[channel]

    async def publish(self, workspace_id: uuid.UUID, event: dict) -> None:
        await self._redis.publish(self._channel(workspace_id), json.dumps(event))

    async def _listen(self, channel: str) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                dead: list[WebSocket] = []
                for ws in list(self._local_sockets.get(channel, [])):
                    try:
                        await ws.send_text(message["data"])
                    except Exception:  # noqa: BLE001 — socket gone; clean it up below
                        dead.append(ws)
                for ws in dead:
                    self._local_sockets[channel].discard(ws)
        finally:
            await pubsub.unsubscribe(channel)


broadcaster = WorkspaceBroadcaster()
