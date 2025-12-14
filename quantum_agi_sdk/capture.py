"""
Screenshot capture utilities
"""

import base64
import io

import mss
from PIL import Image


class ScreenCapture:
    """Captures screenshots for the agent"""

    def __init__(self, monitor: int = 0):
        """
        Initialize screen capture.

        Args:
            monitor: Monitor index to capture (0 = primary)
        """
        self._monitor = monitor
        self._sct = mss.mss()

    def capture(self) -> str:
        """
        Capture a screenshot and return as base64.

        Returns:
            Base64 encoded PNG screenshot
        """
        monitors = self._sct.monitors
        if self._monitor < len(monitors):
            monitor = monitors[self._monitor + 1]
        else:
            monitor = monitors[1]

        sct_img = self._sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def close(self):
        """Close the screen capture resources"""
        self._sct.close()
