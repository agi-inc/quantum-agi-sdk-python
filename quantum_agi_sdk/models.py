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
    FINISH = "finish"
    FAIL = "fail"
    CONFIRM = "confirm"
    ASK_QUESTION = "ask_question"


class ClickAction(BaseModel):
    """Click action at specific coordinates"""

    type: Literal["click", "double_click", "right_click"]
    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")
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


class FinishAction(BaseModel):
    """Task completed successfully"""

    type: Literal["finish"] = "finish"
    message: str = Field(default="", description="Completion message")


class FailAction(BaseModel):
    """Task failed"""

    type: Literal["fail"] = "fail"
    reason: str = Field(..., description="Failure reason")


class ConfirmAction(BaseModel):
    """Request user confirmation for high-impact action"""

    type: Literal["confirm"] = "confirm"
    action_description: str = Field(..., description="Description of action requiring confirmation")
    pending_action: dict = Field(..., description="The action to execute after confirmation")


class AskQuestionAction(BaseModel):
    """Ask the user a question and wait for their text response"""

    type: Literal["ask_question"] = "ask_question"
    question: str = Field(..., description="The question to ask the user")
    context: Optional[str] = Field(default=None, description="Optional context explaining why this information is needed")


Action = Union[
    ClickAction,
    TypeAction,
    KeyAction,
    ScrollAction,
    DragAction,
    WaitAction,
    FinishAction,
    FailAction,
    ConfirmAction,
    AskQuestionAction,
]


class AgentStatus(str, Enum):
    """Current status of the agent"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSE = "pause"
    WAITING_CONFIRMATION = "waiting_confirmation"
    WAITING_QUESTION_ANSWER = "waiting_question_answer"
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

    action_description: str
    pending_action: dict
    context: Optional[dict] = None


class QuestionRequest(BaseModel):
    """Request for user to answer a question"""

    question: str
    context: Optional[str] = None


class TaskResult(BaseModel):
    """Result of a completed task"""

    success: bool
    message: str
    steps_taken: int
    duration_seconds: float
    final_state: Optional[dict] = None


# ============================================================================
# API MODELS (agi-api integration)
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


class ImageUrlContent(BaseModel):
    """Image URL content block"""

    type: Literal["image_url"] = "image_url"
    image_url: dict = Field(..., description="Object with 'url' key containing data URL")


class TextContent(BaseModel):
    """Text content block"""

    type: Literal["text"] = "text"
    text: str


class LLMMessage(BaseModel):
    """Standard LLM message format"""

    role: Literal["user", "assistant"]
    content: Union[str, list[dict]] = Field(..., description="String or list of content blocks")
    tool_calls: Optional[list[dict]] = Field(default=None, description="Tool calls for assistant messages")


class QuantumInferenceRequest(BaseModel):
    """Request for quantum inference step"""

    messages: list[dict] = Field(..., description="Conversation history in standard LLM message format")
    model: Optional[str] = Field(default=None, description="Model to use for inference")


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

    reason: Optional[str] = None


class FinishSessionResponse(BaseModel):
    """Response from finishing a session"""

    id: str
    task: str
    status: str
    step_count: int
    finished_at: Optional[str] = None


