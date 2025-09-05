from pydantic import BaseModel
from typing import Any

class Decision(BaseModel):
    valid: bool
    message: str
    applied: dict[str, Any]
    trace: list[dict[str, Any]]
