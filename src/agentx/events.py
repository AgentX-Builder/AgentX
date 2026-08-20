from enum import Enum
from dataclasses import dataclass
from typing import Any

class EventType(Enum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    ERROR = "error"

@dataclass
class Event:
    type: EventType
    data: Any
