"""fix enum case to match lowercase values

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


ENUM_FIXES = [
    ("plan_name", ["free", "pro", "business"]),
    ("subscription_status", ["active", "trialing", "past_due", "canceled"]),
    ("workspace_role", ["owner", "admin", "agent", "viewer"]),
    ("membership_status", ["active", "invited"]),
    ("conversation_channel", ["widget", "sandbox", "api"]),
    ("conversation_status", ["open", "resolved", "unresolved"]),
    ("message_role", ["user", "assistant", "agent", "system"]),
    ("chat_provider_name", ["openai", "anthropic", "ollama"]),
    ("document_source_type", ["file", "url", "sitemap", "faq", "pasted_text"]),
    ("document_status", ["pending", "parsing", "chunking", "embedding", "ready", "error"]),
]

# Tables and columns that use each enum type
ENUM_COLUMNS = {
    "plan_name": [("subscriptions", "plan")],
    "subscription_status": [("subscriptions", "status")],
    "workspace_role": [("workspace_memberships", "role")],
    "membership_status": [("workspace_memberships", "status")],
    "conversation_channel": [("conversations", "channel")],
    "conversation_status": [("conversations", "status")],
    "message_role": [("messages", "role")],
    "chat_provider_name": [("bots", "chat_provider")],
    "document_source_type": [("documents", "source_type")],
    "document_status": [("documents", "status")],
}


def upgrade() -> None:
    for enum_name, values in ENUM_FIXES:
        # First fix data: lowercase all existing values
        for table, column in ENUM_COLUMNS[enum_name]:
            for val in values:
                # Map uppercase -> lowercase for existing data
                op.execute(f"UPDATE {table} SET {column} = '{val}' WHERE {column}::text = UPPER('{val}')")

        temp_name = f"{enum_name}_new"
        op.execute(f"DROP TYPE IF EXISTS {temp_name}")

        values_str = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {temp_name} AS ENUM ({values_str})")

        for table, column in ENUM_COLUMNS[enum_name]:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {temp_name} USING {column}::text::{temp_name}")

        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
        op.execute(f"ALTER TYPE {temp_name} RENAME TO {enum_name}")


def downgrade() -> None:
    pass  # Downgrade not needed — enum values are now correct
