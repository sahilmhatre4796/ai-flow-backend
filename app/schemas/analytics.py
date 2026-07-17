from pydantic import BaseModel


class RecentQuestion(BaseModel):
    text: str
    asked_at: str


class AnalyticsResponse(BaseModel):
    """Every field is computed live from Conversation/Message/Lead rows.
    Rate/average fields are `None` (never 0% or 0.0) when there isn't yet
    enough data to compute them meaningfully."""
    total_conversations: int
    resolved_count: int
    unresolved_count: int
    open_count: int
    resolution_rate: float | None
    total_leads: int
    leads_from_conversations: int
    total_messages: int
    avg_messages_per_conversation: float | None
    recent_questions: list[RecentQuestion]
