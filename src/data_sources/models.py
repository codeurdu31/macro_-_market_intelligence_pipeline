from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict


class SourceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: Literal["central_bank", "news", "calendar"]
    provider: str
    title: str
    published_at: str
    url: str
    text: str
