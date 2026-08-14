"""
Retrieval-augmented generation: embeds the incoming question, runs a real
pgvector cosine-distance nearest-neighbor query scoped to the bot's *ready*
documents, and only then calls the chat provider — with an honest fallback
when nothing relevant was found, instead of letting the model guess freely.
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot
from app.models.knowledge import Chunk, Document, DocumentStatus
from app.services.ai_providers import get_chat_provider, get_embedding_provider


async def retrieve_relevant_chunks(db: AsyncSession, bot_id: uuid.UUID, query: str, k: int = 4) -> list[Chunk]:
    embedding_provider = get_embedding_provider()
    query_embedding = await asyncio.to_thread(embedding_provider.embed_batch, [query])
    query_embedding = query_embedding[0]

    result = await db.execute(
        select(Chunk)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.bot_id == bot_id,
            Document.status == DocumentStatus.READY,
            Chunk.embedding.isnot(None),
        )
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    return list(result.scalars().all())


def build_context_block(chunks: list[Chunk]) -> str:
    if not chunks:
        return (
            "No relevant knowledge base excerpts were found for this question. "
            "Say so honestly rather than guessing, and offer human handoff."
        )
    excerpts = "\n".join(f"- {c.content}" for c in chunks)
    return f"Relevant knowledge base excerpts:\n{excerpts}"


async def generate_bot_response(db: AsyncSession, bot: Bot, question: str) -> tuple[str, list[Chunk]]:
    chunks = await retrieve_relevant_chunks(db, bot.id, question)
    context_block = build_context_block(chunks)
    system_prompt = (
        f"{bot.persona}\n\n{context_block}\n\n"
        "Answer concisely using only the excerpts above plus general helpfulness. "
        "If you don't know, say so plainly and offer to hand off to a human."
    )
    chat_provider = get_chat_provider(bot.chat_provider.value)
    reply = await chat_provider.generate(system_prompt, question, bot.chat_model)
    return reply or "I'm not sure how to answer that — would you like me to connect you with a person?", chunks
