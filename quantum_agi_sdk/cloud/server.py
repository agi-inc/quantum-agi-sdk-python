"""
FastAPI Cloud Inference Server

This server receives screenshot + context from the CUA SDK and returns
the next optimal action using Claude claude-opus-4-5-20250101.
"""

import base64
import json
import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env and .env.local
load_dotenv()
load_dotenv(".env.local")

import anthropic
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from quantum_agi_sdk.models import InferenceRequest, InferenceResponse


# Tools available to Claude for computer use
COMPUTER_USE_TOOLS = [
    {
        "name": "click",
        "description": "Click at specific coordinates on the screen. Use this for clicking buttons, links, icons, and other UI elements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X coordinate to click (in the 1000x1000 scaled image)"
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate to click (in the 1000x1000 scaled image)"
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button to use",
                    "default": "left"
                }
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "double_click",
        "description": "Double-click at specific coordinates. Use for opening files, selecting words, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"}
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "type",
        "description": "Type text at the current cursor position. Use after clicking on an input field.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "key",
        "description": "Press a key or key combination. Examples: 'enter', 'tab', 'escape', 'ctrl+c', 'cmd+v', 'alt+f4'",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key or key combination to press"
                }
            },
            "required": ["key"]
        }
    },
    {
        "name": "scroll",
        "description": "Scroll at a specific position on the screen",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate to scroll at"},
                "y": {"type": "integer", "description": "Y coordinate to scroll at"},
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Scroll direction"
                },
                "amount": {
                    "type": "integer",
                    "description": "Number of scroll units",
                    "default": 3
                }
            },
            "required": ["x", "y", "direction"]
        }
    },
    {
        "name": "drag",
        "description": "Drag from one point to another. Use for moving windows, selecting text ranges, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"}
            },
            "required": ["start_x", "start_y", "end_x", "end_y"]
        }
    },
    {
        "name": "wait",
        "description": "Wait for a specified duration. Use when waiting for page loads, animations, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds",
                    "default": 1.0
                }
            }
        }
    },
    {
        "name": "done",
        "description": "Signal that the task has been completed successfully",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Completion message describing what was accomplished"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "fail",
        "description": "Signal that the task cannot be completed",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason why the task failed"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "confirm",
        "description": "Request user confirmation for a high-impact action (e.g., purchase, booking, subscription, OS changes)",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_description": {
                    "type": "string",
                    "description": "Clear description of the action requiring confirmation"
                },
                "impact_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Impact level of the action"
                },
                "pending_action": {
                    "type": "object",
                    "description": "The action to execute after confirmation"
                }
            },
            "required": ["action_description", "pending_action"]
        }
    }
]


# High-impact keywords that should trigger confirmation
HIGH_IMPACT_KEYWORDS = [
    "purchase", "buy", "checkout", "payment", "pay now", "confirm order",
    "subscribe", "subscription", "sign up", "create account",
    "book", "reserve", "confirm booking", "complete reservation",
    "delete", "remove", "uninstall", "format", "reset",
    "send", "submit", "publish", "post",
    "agree", "accept terms", "i agree",
]


class InferenceEngine:
    """Handles inference using Claude claude-opus-4-5-20250101"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        """
        Process a screenshot and determine the next action.

        Args:
            request: Inference request with screenshot and context

        Returns:
            InferenceResponse with the next action
        """
        # Build the system prompt
        system_prompt = self._build_system_prompt(request)

        # Build messages with the screenshot
        messages = self._build_messages(request)

        # Call Claude with tools
        response = self.client.messages.create(
            model="claude-opus-4-5-20250101",
            max_tokens=1024,
            system=system_prompt,
            tools=COMPUTER_USE_TOOLS,
            messages=messages,
        )

        # Parse the response
        return self._parse_response(response, request)

    def _build_system_prompt(self, request: InferenceRequest) -> str:
        """Build the system prompt for Claude"""
        context_str = ""
        if request.context:
            context_str = f"\n\nUser Context from Quantum:\n{json.dumps(request.context, indent=2)}"

        return f"""You are an AI agent controlling a computer to complete tasks for users.
You are part of the AGI Computer Use Agent system integrated with Lenovo's Quantum.

Your job is to analyze the screenshot and determine the single best next action to take.

IMPORTANT GUIDELINES:
1. You can ONLY see the current screenshot. Base your decision solely on what's visible.
2. The screenshot has been scaled to 1000x1000 pixels. Provide coordinates in this scale.
3. Take ONE action at a time. Don't try to plan multiple steps ahead.
4. Be precise with click coordinates - aim for the center of buttons/links.
5. For high-impact actions (purchases, bookings, subscriptions, account changes, deletions),
   ALWAYS use the 'confirm' tool to request user confirmation first.
6. If you cannot see what you need, try scrolling or navigating to find it.
7. If the task appears complete, use the 'done' tool.
8. If you're stuck or the task is impossible, use the 'fail' tool.

Current Task: {request.task}
Step Number: {request.step_number}
{context_str}

Previous actions taken:
{self._format_history(request.history)}

Analyze the screenshot and call the appropriate tool for the next action."""

    def _build_messages(self, request: InferenceRequest) -> list:
        """Build the messages array with the screenshot"""
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": request.screenshot_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Current screenshot. What is the next action to complete: {request.task}"
                    }
                ],
            }
        ]

    def _format_history(self, history: list) -> str:
        """Format action history for context"""
        if not history:
            return "None yet"

        formatted = []
        for i, action in enumerate(history[-5:], 1):  # Last 5 actions
            action_type = action.get("type", "unknown")
            if action_type == "click":
                formatted.append(f"{i}. Clicked at ({action.get('x')}, {action.get('y')})")
            elif action_type == "type":
                text = action.get("text", "")[:50]
                formatted.append(f"{i}. Typed: '{text}'")
            elif action_type == "key":
                formatted.append(f"{i}. Pressed key: {action.get('key')}")
            elif action_type == "scroll":
                formatted.append(f"{i}. Scrolled {action.get('direction')}")
            else:
                formatted.append(f"{i}. {action_type}")

        return "\n".join(formatted)

    def _parse_response(
        self, response: anthropic.types.Message, request: InferenceRequest
    ) -> InferenceResponse:
        """Parse Claude's response into an InferenceResponse"""
        reasoning = None
        action = None

        for block in response.content:
            if block.type == "text":
                reasoning = block.text
            elif block.type == "tool_use":
                action = {
                    "type": block.name,
                    **block.input
                }

        if not action:
            # No tool was called, default to fail
            action = {
                "type": "fail",
                "reason": "Model did not return a valid action"
            }

        # Check if this action should require confirmation
        requires_confirmation = self._should_require_confirmation(action, reasoning)

        return InferenceResponse(
            action=action,
            reasoning=reasoning,
            confidence=1.0,
            requires_confirmation=requires_confirmation,
        )

    def _should_require_confirmation(
        self, action: dict, reasoning: Optional[str]
    ) -> bool:
        """Check if an action should require user confirmation"""
        # Confirm actions already require confirmation by design
        if action.get("type") == "confirm":
            return False  # Already handled

        # Check for high-impact patterns
        action_type = action.get("type")

        # Type actions with high-impact text
        if action_type == "type":
            text = action.get("text", "").lower()
            for keyword in HIGH_IMPACT_KEYWORDS:
                if keyword in text:
                    return True

        # Check reasoning for high-impact indicators
        if reasoning:
            reasoning_lower = reasoning.lower()
            for keyword in HIGH_IMPACT_KEYWORDS:
                if keyword in reasoning_lower:
                    return True

        return False


def create_app(api_key: Optional[str] = None) -> FastAPI:
    """Create the FastAPI application"""
    app = FastAPI(
        title="AGI CUA Cloud Inference API",
        description="Cloud inference server for the Quantum AGI Computer Use Agent",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize inference engine
    engine: Optional[InferenceEngine] = None

    @app.on_event("startup")
    async def startup():
        nonlocal engine
        try:
            engine = InferenceEngine(api_key)
        except ValueError as e:
            print(f"Warning: {e}. Set ANTHROPIC_API_KEY to enable inference.")

    @app.get("/health")
    async def health():
        """Health check endpoint"""
        return {"status": "healthy", "engine_ready": engine is not None}

    @app.post("/v1/inference", response_model=InferenceResponse)
    async def inference(
        request: InferenceRequest,
        authorization: Optional[str] = Header(None),
    ):
        """
        Process a screenshot and return the next action.

        This is the main inference endpoint called by the CUA SDK.
        """
        if not engine:
            raise HTTPException(
                status_code=503,
                detail="Inference engine not initialized. Check ANTHROPIC_API_KEY.",
            )

        try:
            return engine.infer(request)
        except anthropic.APIError as e:
            raise HTTPException(status_code=502, detail=f"Claude API error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    @app.get("/v1/tools")
    async def get_tools():
        """Get available tools/actions"""
        return {"tools": COMPUTER_USE_TOOLS}

    return app


# CLI entry point
def main():
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
