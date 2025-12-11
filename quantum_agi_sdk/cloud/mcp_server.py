"""
MCP (Model Context Protocol) Server for Quantum AGI SDK

This server exposes the CUA inference capabilities via MCP, allowing
AI assistants like Claude to invoke the computer use agent.
"""

import json
import os
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from quantum_agi_sdk.cloud.server import InferenceEngine, COMPUTER_USE_TOOLS
from quantum_agi_sdk.models import InferenceRequest

# Load environment variables
load_dotenv()
load_dotenv(".env.local")

# Create the MCP server using FastMCP
mcp = FastMCP("quantum-agi-cua", json_response=True)

# Global inference engine
_engine: Optional[InferenceEngine] = None


def get_engine() -> InferenceEngine:
    """Get or create the inference engine"""
    global _engine
    if _engine is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        _engine = InferenceEngine(api_key)
    return _engine


@mcp.tool()
def cua_start_task(task: str, context: dict | None = None) -> dict:
    """
    Start a computer use agent task.

    The agent will analyze screenshots and execute actions to complete the task.

    Args:
        task: The task to complete (e.g., 'Open Chrome and search for Lenovo laptops')
        context: Optional context including user preferences, memories, etc.

    Returns:
        Instructions for how to proceed with the task
    """
    return {
        "status": "ready",
        "message": f"Task '{task}' is ready to begin. Use cua_infer_action with screenshots to get actions.",
        "task": task,
        "context": context or {},
        "instructions": [
            "1. Capture a screenshot of the current screen",
            "2. Scale it to 1000x1000 pixels",
            "3. Call cua_infer_action with the screenshot",
            "4. Execute the returned action locally",
            "5. Repeat until done or fail action is returned"
        ]
    }


@mcp.tool()
def cua_infer_action(
    task: str,
    screenshot_base64: str,
    original_width: int,
    original_height: int,
    history: list[dict] | None = None,
    step_number: int = 0,
    context: dict | None = None
) -> dict:
    """
    Given a screenshot, determine the next action to take for a task.

    Args:
        task: The task being worked on
        screenshot_base64: Base64 encoded screenshot (should be scaled to 1000x1000)
        original_width: Original screenshot width before scaling
        original_height: Original screenshot height before scaling
        history: Previous actions taken
        step_number: Current step number
        context: Optional context

    Returns:
        The next action to execute with reasoning
    """
    try:
        engine = get_engine()

        request = InferenceRequest(
            task=task,
            screenshot_base64=screenshot_base64,
            original_width=original_width,
            original_height=original_height,
            context=context,
            history=history or [],
            step_number=step_number
        )

        response = engine.infer(request)

        return {
            "action": response.action,
            "reasoning": response.reasoning,
            "confidence": response.confidence,
            "requires_confirmation": response.requires_confirmation,
            "estimated_remaining_steps": response.estimated_remaining_steps,
            "note": "Coordinates are in inference scale (1000x1000). Use cua_scale_coordinates to convert to original screen coordinates before executing."
        }

    except Exception as e:
        return {
            "error": str(e),
            "action": {"type": "fail", "reason": str(e)}
        }


@mcp.tool()
def cua_get_available_actions() -> dict:
    """
    Get the list of available computer control actions that the agent can perform.

    Returns:
        List of available actions with their schemas
    """
    return {
        "actions": COMPUTER_USE_TOOLS,
        "note": "These are the actions the agent can return. Coordinates should be in 1000x1000 scale."
    }


@mcp.tool()
def cua_scale_coordinates(
    x: int,
    y: int,
    original_width: int,
    original_height: int
) -> dict:
    """
    Scale coordinates from inference size (1000x1000) back to original screen coordinates.

    Args:
        x: X coordinate in inference scale (0-1000)
        y: Y coordinate in inference scale (0-1000)
        original_width: Original screen width
        original_height: Original screen height

    Returns:
        Scaled coordinates in original screen dimensions
    """
    from quantum_agi_sdk.capture import scale_coordinates_to_original

    scaled_x, scaled_y = scale_coordinates_to_original(x, y, original_width, original_height)

    return {
        "original_coordinates": {"x": x, "y": y},
        "scaled_coordinates": {"x": scaled_x, "y": scaled_y},
        "original_screen_size": {"width": original_width, "height": original_height}
    }


def main():
    """Entry point for the MCP server"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
