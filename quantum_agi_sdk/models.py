"""
Data models for the Quantum AGI SDK
"""

import re
import json
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions the agent can perform"""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TRIPLE_CLICK = "triple_click"
    HOVER = "hover"
    TYPE = "type"
    KEY = "key"
    SCROLL = "scroll"
    DRAG = "drag"
    WAIT = "wait"
    FINISH = "finish"
    FAIL = "fail"
    CONFIRM = "confirm"
    ASK_QUESTION = "ask_question"


class ClickAction(BaseModel):
    """Click action at specific coordinates"""

    type: Literal["click", "double_click", "right_click", "triple_click"]
    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")


class HoverAction(BaseModel):
    """Hover action - move mouse without clicking"""

    type: Literal["hover"] = "hover"
    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")


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
    amount: Optional[int] = Field(default=None, description="Number of scroll units")


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
    duration: Optional[float] = Field(default=None, description="Duration in seconds")


class FinishAction(BaseModel):
    """Task completed successfully"""

    type: Literal["finish"] = "finish"
    message: Optional[str] = Field(default=None, description="Completion message")


class FailAction(BaseModel):
    """Task failed"""

    type: Literal["fail"] = "fail"
    reason: str = Field(..., description="Failure reason")


class ConfirmAction(BaseModel):
    """Request user confirmation for high-impact action"""

    type: Literal["confirm"] = "confirm"
    message: str = Field(..., description="Message to show to the user")


class AskQuestionAction(BaseModel):
    """Ask the user a question and wait for their text response"""

    type: Literal["ask_question"] = "ask_question"
    question: str = Field(..., description="The question to ask the user")


Action = Union[
    ClickAction,
    HoverAction,
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


class TaskResult(BaseModel):
    """Result of a completed task"""

    success: bool
    message: str
    steps_taken: int
    duration_seconds: float
    final_state: Optional[dict] = None


# ============================================================================
# API MODELS (quantum-agi-cloud integration)
# ============================================================================


class GetActionRequest(BaseModel):
    """Request to the /get_action endpoint"""

    session_id: str = Field(..., description="Session ID for this run")
    image: str = Field(..., description="Base64 encoded screenshot")
    prompt: str = Field(..., description="Task prompt")
    phone_state: str = Field(default="", description="Not used for desktop")
    installed_packages: str = Field(default="", description="Not used for desktop")
    think: bool = Field(default=True, description="Whether to use thinking")
    agent_type: str = Field(default="agi-0", description="Agent type: agi-0 or agi-1-preview")
    user_id: Optional[str] = Field(default=None, description="User ID for tracking")
    platform: str = Field(default="desktop", description="Platform identifier")
    run_type: str = Field(default="user_traffic", description="Run type")
    data_version: Optional[str] = Field(default=None, description="Data version")


class GetActionResponse(BaseModel):
    """Response from the /get_action endpoint"""

    success: bool
    action: str = Field(..., description="Action string like click({...})")
    session_id: str
    image_count: int


def parse_action_string(action_string: str) -> dict:
    """Parse an action string like 'click({"x":100,"y":200})' into a dict.

    Args:
        action_string: Action string from the cloud API

    Returns:
        Dictionary with 'type' and action parameters
    """
    match = re.match(r'^(\w+)\s*\((.*)\)\s*$', action_string.strip(), re.DOTALL)

    if not match:
        raise ValueError(f"Invalid action format: {action_string}")

    action_name = match.group(1)
    json_part = match.group(2).strip()

    result = {"type": action_name}

    # Parse JSON arguments if present
    if json_part:
        try:
            args = json.loads(json_part)

            # Handle point_2d format: [x, y]
            if "point_2d" in args and isinstance(args["point_2d"], list):
                arr = args["point_2d"]
                if len(arr) >= 2:
                    result["x"] = arr[0]
                    result["y"] = arr[1]
                del args["point_2d"]

            # Handle start_point_2d and end_point_2d for drag
            if "start_point_2d" in args and isinstance(args["start_point_2d"], list):
                arr = args["start_point_2d"]
                if len(arr) >= 2:
                    result["start_x"] = arr[0]
                    result["start_y"] = arr[1]
                del args["start_point_2d"]

            if "end_point_2d" in args and isinstance(args["end_point_2d"], list):
                arr = args["end_point_2d"]
                if len(arr) >= 2:
                    result["end_x"] = arr[0]
                    result["end_y"] = arr[1]
                del args["end_point_2d"]

            # Add remaining args
            result.update(args)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in action: {action_string}") from e

    return result
