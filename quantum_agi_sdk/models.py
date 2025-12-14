"""
Data models for the Quantum AGI SDK
"""

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions the agent can perform"""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    KEY = "key"
    SCROLL = "scroll"
    DRAG = "drag"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    DONE = "done"
    FAIL = "fail"
    CONFIRM = "confirm"


class ClickAction(BaseModel):
    """Click action at specific coordinates"""

    type: Literal["click", "double_click", "right_click"]
    x: int = Field(..., description="X coordinate (in original screen scale)")
    y: int = Field(..., description="Y coordinate (in original screen scale)")
    button: str = Field(default="left", description="Mouse button: left, right, middle")


class TypeAction(BaseModel):
    """Type text action"""

    type: Literal["type"] = "type"
    text: str = Field(..., description="Text to type")


class KeyAction(BaseModel):
    """Press key or key combination"""

    type: Literal["key"] = "key"
    key: str = Field(..., description="Key to press (e.g., 'enter', 'ctrl+c', 'cmd+v')")


class ScrollAction(BaseModel):
    """Scroll action"""

    type: Literal["scroll"] = "scroll"
    x: int = Field(..., description="X coordinate to scroll at")
    y: int = Field(..., description="Y coordinate to scroll at")
    direction: str = Field(..., description="Scroll direction: up, down, left, right")
    amount: int = Field(default=3, description="Number of scroll units")


class DragAction(BaseModel):
    """Drag from one point to another"""

    type: Literal["drag"] = "drag"
    start_x: int
    start_y: int
    end_x: int
    end_y: int


class WaitAction(BaseModel):
    """Wait for specified duration"""

    type: Literal["wait"] = "wait"
    duration: float = Field(default=1.0, description="Duration in seconds")


class DoneAction(BaseModel):
    """Task completed successfully"""

    type: Literal["done"] = "done"
    message: str = Field(default="", description="Completion message")


class FailAction(BaseModel):
    """Task failed"""

    type: Literal["fail"] = "fail"
    reason: str = Field(..., description="Failure reason")


class ConfirmAction(BaseModel):
    """Request user confirmation for high-impact action"""

    type: Literal["confirm"] = "confirm"
    action_description: str = Field(..., description="Description of action requiring confirmation")
    impact_level: str = Field(default="high", description="Impact level: low, medium, high")
    pending_action: dict = Field(..., description="The action to execute after confirmation")


Action = Union[
    ClickAction,
    TypeAction,
    KeyAction,
    ScrollAction,
    DragAction,
    WaitAction,
    DoneAction,
    FailAction,
    ConfirmAction,
]


class AgentStatus(str, Enum):
    """Current status of the agent"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSE = "pause"
    WAITING_CONFIRMATION = "waiting_confirmation"
    FINISH = "finish"
    FAIL = "fail"


class AgentState(BaseModel):
    """Current state of the agent"""

    status: AgentStatus = AgentStatus.IDLE
    task: Optional[str] = None
    current_step: int = 0
    total_steps: Optional[int] = None
    last_action: Optional[Action] = None
    progress_message: Optional[str] = None
    error: Optional[str] = None


class ConfirmationRequest(BaseModel):
    """Request for user confirmation"""

    id: str
    action_description: str
    impact_level: str
    pending_action: dict
    context: Optional[dict] = None


class TaskResult(BaseModel):
    """Result of a completed task"""

    success: bool
    message: str
    steps_taken: int
    duration_seconds: float
    final_state: Optional[dict] = None


class InferenceRequest(BaseModel):
    """Request to the cloud inference API"""

    task: str = Field(..., description="User task/intent from Quantum")
    screenshot_base64: str = Field(..., description="Base64 encoded screenshot (scaled to 1000x1000)")
    original_width: int = Field(..., description="Original screenshot width")
    original_height: int = Field(..., description="Original screenshot height")
    context: Optional[dict] = Field(default=None, description="Additional context from Quantum")
    history: list[dict] = Field(default_factory=list, description="Previous actions taken")
    step_number: int = Field(default=0, description="Current step number")


class InferenceResponse(BaseModel):
    """Response from the cloud inference API"""

    action: dict = Field(..., description="Next action to execute")
    reasoning: Optional[str] = Field(default=None, description="Model's reasoning")
    confidence: float = Field(default=1.0, description="Confidence score 0-1")
    requires_confirmation: bool = Field(default=False)
    estimated_remaining_steps: Optional[int] = None


# ============================================================================
# NEW API MODELS (agi-api integration)
# ============================================================================


class StartSessionRequest(BaseModel):
    """Request to start a quantum agent session"""

    task: str = Field(..., description="Task/goal for the agent")
    device_id: Optional[str] = Field(default=None, description="Optional device ID")
    context: Optional[dict] = Field(default=None, description="Optional context")


class StartSessionResponse(BaseModel):
    """Response from starting a session"""

    id: str = Field(..., description="Session UUID")
    task: str
    status: str
    step_count: int
    device_id: Optional[str] = None
    started_at: Optional[str] = None
    created_at: Optional[str] = None


class QuantumInferenceRequest(BaseModel):
    """Request for quantum inference step"""

    screenshot_base64: str = Field(..., description="Base64-encoded PNG screenshot")
    history: list[dict] = Field(default_factory=list)
    model: Optional[str] = Field(
        None,
        description="Model to use for inference (e.g., 'anthropic/claude-sonnet-4', 'openai/gpt-4o')",
    )


class QuantumInferenceResponse(BaseModel):
    """Response from quantum inference"""

    session_id: str
    step_number: int
    action: dict
    reasoning: Optional[str] = None
    confidence: float = 1.0
    requires_confirmation: bool = False


class FinishSessionRequest(BaseModel):
    """Request to finish a session"""

    status: Literal["finish", "fail"] = Field(default="finish", description="finish or fail")
    reason: Optional[str] = None


class FinishSessionResponse(BaseModel):
    """Response from finishing a session"""

    id: str
    task: str
    status: str
    step_count: int
    finished_at: Optional[str] = None


class InterruptRequest(BaseModel):
    """Request to interrupt the agent with a user message"""

    message: str = Field(..., description="User's interruption message")


class InterruptResponse(BaseModel):
    """Response from interrupting the agent"""

    success: bool
    message: Optional[str] = None
    timestamp: Optional[str] = None
