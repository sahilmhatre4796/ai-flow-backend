from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, model_validator


class ResponseBase(BaseModel):
    """Base for all API response schemas.

    SQLAlchemy models use native ``uuid.UUID`` primary keys (and foreign
    keys), but the API serialises every ID as a plain string.  Pydantic v2
    with ``from_attributes = True`` does **not** automatically coerce
    ``UUID → str``, so we add a ``before`` validator that handles it.
    """

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _coerce_uuids_to_str(cls, data):  # noqa: N805
        if isinstance(data, dict):
            return {
                k: str(v) if isinstance(v, UUID) else v
                for k, v in data.items()
            }
        # from_attributes mode — data is an ORM object
        for field_name in getattr(data, "__dict__", {}):
            val = getattr(data, field_name, None)
            if isinstance(val, UUID):
                try:
                    setattr(data, field_name, str(val))
                except Exception:
                    pass
        return data
