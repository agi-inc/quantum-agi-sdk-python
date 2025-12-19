"""
Local action executor - executes actions on the device
"""

import platform
import time
from typing import Optional, Tuple

import mss
import pyautogui

from quantum_agi_sdk.models import (
    Action,
    ClickAction,
    DragAction,
    KeyAction,
    ScrollAction,
    TypeAction,
    WaitAction,
)

# Configure pyautogui for safety
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

# Cache for DPI scale factor
_cached_scale_factor: Optional[float] = None


def get_scale_factor() -> float:
    """
    Get the DPI scale factor for the primary monitor.

    Screenshots (via mss) are in physical pixels, but pyautogui clicks
    use logical coordinates. On HiDPI displays (e.g., Retina), we need
    to divide physical coordinates by the scale factor.

    Returns:
        Scale factor (e.g., 2.0 for Retina displays, 1.0 for standard)
    """
    global _cached_scale_factor
    if _cached_scale_factor is not None:
        return _cached_scale_factor

    try:
        # Get physical size from mss (what screenshots capture)
        with mss.mss() as sct:
            # monitors[0] is "all monitors", monitors[1] is primary
            primary = sct.monitors[1]
            physical_width = primary["width"]
            physical_height = primary["height"]

        # Get logical size from pyautogui (what clicks use)
        logical_width, logical_height = pyautogui.size()

        # Calculate scale factor (use width, but height should match)
        if logical_width > 0:
            _cached_scale_factor = physical_width / logical_width
        else:
            _cached_scale_factor = 1.0
    except Exception:
        _cached_scale_factor = 1.0

    return _cached_scale_factor


def to_logical_coords(x: int, y: int) -> Tuple[int, int]:
    """
    Convert physical (screenshot) coordinates to logical (click) coordinates.

    Args:
        x: Physical X coordinate
        y: Physical Y coordinate

    Returns:
        Tuple of (logical_x, logical_y)
    """
    scale = get_scale_factor()
    return (round(x / scale), round(y / scale))


class ActionExecutor:
    """Executes actions locally on the device"""

    def __init__(self, failsafe: bool = True, pause: float = 0.1):
        """
        Initialize the action executor.

        Args:
            failsafe: Enable pyautogui failsafe (move mouse to corner to abort)
            pause: Pause between actions in seconds
        """
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = pause
        self._platform = platform.system().lower()

    def execute(self, action: dict) -> bool:
        """
        Execute an action on the local device.

        Args:
            action: Action dictionary to execute

        Returns:
            True if action executed successfully
        """
        action_type = action.get("type")

        if action_type in ("click", "double_click", "right_click", "triple_click"):
            return self._execute_click(action)
        elif action_type == "hover":
            return self._execute_hover(action)
        elif action_type == "type":
            return self._execute_type(action)
        elif action_type == "key":
            return self._execute_key(action)
        elif action_type == "scroll":
            return self._execute_scroll(action)
        elif action_type == "drag":
            return self._execute_drag(action)
        elif action_type == "wait":
            return self._execute_wait(action)
        elif action_type in ("finish", "fail", "confirm", "ask_question"):
            # These are control actions, not device actions
            return True
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    def _execute_click(self, action: dict) -> bool:
        """Execute a click action"""
        # Convert from physical (screenshot) to logical (click) coordinates
        x, y = to_logical_coords(action["x"], action["y"])
        action_type = action["type"]
        button = action.get("button", "left")

        if action_type == "double_click":
            pyautogui.doubleClick(x, y, button=button)
        elif action_type == "triple_click":
            pyautogui.tripleClick(x, y, button=button)
        elif action_type == "right_click":
            pyautogui.rightClick(x, y)
        else:
            pyautogui.click(x, y, button=button)

        return True

    def _execute_hover(self, action: dict) -> bool:
        """Execute a hover (move mouse) action"""
        # Convert from physical (screenshot) to logical (click) coordinates
        x, y = to_logical_coords(action["x"], action["y"])
        pyautogui.moveTo(x, y)
        return True

    def _execute_type(self, action: dict) -> bool:
        """Execute a type action"""
        text = action.get("text") or action.get("content") or ""
        # Use interval for more natural typing
        pyautogui.write(text, interval=0.02)
        return True

    def _execute_key(self, action: dict) -> bool:
        """Execute a key press action"""
        key = action["key"]

        # Handle key combinations (e.g., "ctrl+c", "cmd+v")
        if "+" in key:
            keys = key.split("+")
            # Normalize key names
            keys = [self._normalize_key(k.strip()) for k in keys]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(self._normalize_key(key))

        return True

    def _normalize_key(self, key: str) -> str:
        """Normalize key names across platforms"""
        key = key.lower()

        # Handle platform-specific keys
        if self._platform == "darwin":
            if key in ("ctrl", "control"):
                return "ctrl"
            if key in ("cmd", "command", "meta"):
                return "command"
        else:
            if key in ("cmd", "command", "meta"):
                return "ctrl"

        # Common key mappings
        key_map = {
            "return": "enter",
            "esc": "escape",
            "del": "delete",
            "backspace": "backspace",
        }

        return key_map.get(key, key)

    def _execute_scroll(self, action: dict) -> bool:
        """Execute a scroll action"""
        x = action.get("x")
        y = action.get("y")
        direction = action["direction"]
        amount = action.get("amount", 3)

        # Move to position if specified (convert from physical to logical)
        if x is not None and y is not None:
            logical_x, logical_y = to_logical_coords(x, y)
            pyautogui.moveTo(logical_x, logical_y)

        # Convert direction to scroll amount
        if direction == "up":
            pyautogui.scroll(amount)
        elif direction == "down":
            pyautogui.scroll(-amount)
        elif direction == "left":
            pyautogui.hscroll(-amount)
        elif direction == "right":
            pyautogui.hscroll(amount)

        return True

    def _execute_drag(self, action: dict) -> bool:
        """Execute a drag action"""
        # Convert from physical (screenshot) to logical (click) coordinates
        start_x, start_y = to_logical_coords(action["start_x"], action["start_y"])
        end_x, end_y = to_logical_coords(action["end_x"], action["end_y"])

        pyautogui.moveTo(start_x, start_y)
        pyautogui.drag(end_x - start_x, end_y - start_y, duration=0.5)

        return True

    def _execute_wait(self, action: dict) -> bool:
        """Execute a wait action"""
        duration = action.get("duration", 1.0)
        time.sleep(duration)
        return True

    def get_screen_size(self) -> tuple[int, int]:
        """Get the current screen size"""
        return pyautogui.size()

    def get_mouse_position(self) -> tuple[int, int]:
        """Get current mouse position"""
        return pyautogui.position()
