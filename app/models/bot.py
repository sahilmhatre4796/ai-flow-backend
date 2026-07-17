import enum
import secrets
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ChatProviderName(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


def generate_public_key() -> str:
    # Identifies the bot to the public embed script — never reveals workspace
    # internals and carries no privileges beyond "which bot to talk to".
    return f"afk_pub_{secrets.token_urlsafe(18)}"


class Bot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bots"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    persona: Mapped[str] = mapped_column(Text, nullable=False)
    chat_provider: Mapped[ChatProviderName] = mapped_column(
        Enum(ChatProviderName, name="chat_provider_name"), nullable=False
    )
    chat_model: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    public_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, default=generate_public_key
    )
    widget_color: Mapped[str] = mapped_column(String(9), default="#818cf8", nullable=False)
    widget_position: Mapped[str] = mapped_column(String(20), default="bottom-right", nullable=False)

    documents: Mapped[list["Document"]] = relationship(back_populates="bot", cascade="all, delete-orphan")  # noqa: F821
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="bot", cascade="all, delete-orphan")  # noqa: F821
