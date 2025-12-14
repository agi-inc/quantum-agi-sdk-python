"""
Quantum AGI SDK - Computer Use Agent for Quantum Integration
"""

from quantum_agi_sdk.client import CUAClient
from quantum_agi_sdk.models import (
    Action,
    ActionType,
    AgentState,
    AgentStatus,
    ClickAction,
    ConfirmationRequest,
    KeyAction,
    ScrollAction,
    TaskResult,
    TypeAction,
)

__version__ = "0.1.0"

__all__ = [
    "CUAClient",
    "Action",
    "ActionType",
    "AgentState",
    "AgentStatus",
    "ClickAction",
    "TypeAction",
    "ScrollAction",
    "KeyAction",
    "ConfirmationRequest",
    "TaskResult",
]
