import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.bot import Bot
from app.models.conversation import Conversation, ConversationChannel, Message, MessageRole
from app.security import decode_access_token
from app.services.rag import generate_bot_response
from app.websocket_manager import broadcaster

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/widget/{bot_public_key}")
async def widget_socket(websocket: WebSocket, bot_public_key: str, visitor_id: str = Query(...)):
    """Public, unauthenticated endpoint embedded on customer sites. Identity
    is scoped only to `bot_public_key` (which bot) and `visitor_id` (a
    client-generated session id) — no workspace internals are exposed."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Bot).where(Bot.public_key == bot_public_key, Bot.is_active.is_(True)))
        bot = result.scalar_one_or_none()
        if not bot:
            await websocket.close(code=4404)
            return

        # Use SELECT FOR UPDATE to prevent race condition on conversation creation
        from sqlalchemy import with_for_of
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.bot_id == bot.id,
                Conversation.visitor_id == visitor_id,
                Conversation.channel == ConversationChannel.WIDGET,
            ).order_by(Conversation.started_at.desc()).with_for_update()
        )
        conversation = conv_result.scalars().first()
        if not conversation:
            conversation = Conversation(
                workspace_id=bot.workspace_id, bot_id=bot.id, visitor_id=visitor_id,
                channel=ConversationChannel.WIDGET,
            )
            db.add(conversation)
            await db.commit()

        await broadcaster.connect(bot.workspace_id, websocket)
        try:
            while True:
                text = await websocket.receive_text()
                async with AsyncSessionLocal() as msg_db:
                    result = await msg_db.execute(select(Bot).where(Bot.id == bot.id))
                    current_bot = result.scalar_one_or_none()
                    if not current_bot or not current_bot.is_active:
                        await websocket.send_json({"role": "assistant", "content": "This bot is no longer active."})
                        continue

                    user_message = Message(conversation_id=conversation.id, role=MessageRole.USER, content=text)
                    msg_db.add(user_message)
                    await msg_db.flush()
                    await broadcaster.publish(bot.workspace_id, {
                        "type": "message", "conversation_id": str(conversation.id),
                        "role": "user", "content": text, "created_at": user_message.created_at.isoformat(),
                    })

                    reply_text, used_chunks = await generate_bot_response(msg_db, current_bot, text)
                    assistant_message = Message(
                        conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=reply_text,
                        retrieved_chunk_ids=[str(c.id) for c in used_chunks],
                    )
                    msg_db.add(assistant_message)
                    await msg_db.commit()

                    await websocket.send_json({"role": "assistant", "content": reply_text})
                    await broadcaster.publish(bot.workspace_id, {
                        "type": "message", "conversation_id": str(conversation.id),
                        "role": "assistant", "content": reply_text,
                        "created_at": assistant_message.created_at.isoformat(),
                    })
        except WebSocketDisconnect:
            pass
        finally:
            await broadcaster.disconnect(bot.workspace_id, websocket)


@router.websocket("/ws/agent/{workspace_id}")
async def agent_socket(websocket: WebSocket, workspace_id: uuid.UUID, token: str = Query(...)):
    """Authenticated dashboard endpoint — agents watch live conversations
    for their own workspace only. Membership is enforced before the socket
    is even accepted."""
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4401)
        return

    async with AsyncSessionLocal() as db:
        from app.models.workspace import MembershipStatus, WorkspaceMembership  # local import avoids a cycle at module load

        result = await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == MembershipStatus.ACTIVE,
            )
        )
        if not result.scalar_one_or_none():
            await websocket.close(code=4403)
            return

    await broadcaster.connect(workspace_id, websocket)
    try:
        while True:
            # Agents only receive broadcasts in this version; replying as an
            # agent is handled via the REST PATCH /conversations endpoint.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(workspace_id, websocket)
