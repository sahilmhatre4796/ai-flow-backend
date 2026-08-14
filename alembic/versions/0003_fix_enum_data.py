"""fix existing data to use lowercase enum values

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Fix any rows that still have UPPERCASE enum values stored as text
    # The enum types were recreated in 0002 but existing data wasn't updated
    fixes = [
        ("subscriptions", "plan", [("FREE", "free"), ("PRO", "pro"), ("BUSINESS", "business")]),
        ("subscriptions", "status", [("ACTIVE", "active"), ("TRIALING", "trialing"), ("PAST_DUE", "past_due"), ("CANCELED", "canceled")]),
        ("workspace_memberships", "role", [("OWNER", "owner"), ("ADMIN", "admin"), ("AGENT", "agent"), ("VIEWER", "viewer")]),
        ("workspace_memberships", "status", [("ACTIVE", "active"), ("INVITED", "invited")]),
        ("conversations", "channel", [("WIDGET", "widget"), ("SANDBOX", "sandbox"), ("API", "api")]),
        ("conversations", "status", [("OPEN", "open"), ("RESOLVED", "resolved"), ("UNRESOLVED", "unresolved")]),
        ("messages", "role", [("USER", "user"), ("ASSISTANT", "assistant"), ("AGENT", "agent"), ("SYSTEM", "system")]),
        ("bots", "chat_provider", [("OPENAI", "openai"), ("ANTHROPIC", "anthropic"), ("OLLAMA", "ollama")]),
        ("documents", "source_type", [("FILE", "file"), ("URL", "url"), ("SITEMAP", "sitemap"), ("FAQ", "faq"), ("PASTED_TEXT", "pasted_text")]),
        ("documents", "status", [("PENDING", "pending"), ("PARSING", "parsing"), ("CHUNKING", "chunking"), ("EMBEDDING", "embedding"), ("READY", "ready"), ("ERROR", "error")]),
    ]
    for table, column, mappings in fixes:
        for old_val, new_val in mappings:
            op.execute(f"UPDATE {table} SET {column} = '{new_val}' WHERE {column}::text = '{old_val}'")


def downgrade() -> None:
    pass
