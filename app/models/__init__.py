"""
Import every model module here so that:
  1. `Base.metadata` knows about all tables (required for Alembic autogenerate
     and for `env.py`'s `target_metadata`).
  2. SQLAlchemy can resolve string-based relationship() references between
     modules regardless of import order elsewhere in the app.
"""
from app.models.user import User, RefreshToken, EmailVerificationToken, PasswordResetToken
from app.models.workspace import Workspace, WorkspaceMembership
from app.models.bot import Bot
from app.models.knowledge import Document, Chunk
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.models.billing import Subscription
from app.models.template import Template, TemplateInstall
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog

__all__ = [
    "User", "RefreshToken", "EmailVerificationToken", "PasswordResetToken",
    "Workspace", "WorkspaceMembership",
    "Bot",
    "Document", "Chunk",
    "Conversation", "Message",
    "Lead",
    "Subscription",
    "Template", "TemplateInstall",
    "ApiKey",
    "AuditLog",
]
