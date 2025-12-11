"""
Screenshot capture and scaling utilities
"""

import base64
import io
from typing import Optional

import mss
from PIL import Image

# Target size for inference (as per spec)
INFERENCE_SIZE = (1000, 1000)


class ScreenCapture:
    """Captures and processes screenshots for the agent"""

    def __init__(self, monitor: int = 0):
        """
        Initialize screen capture.

        Args:
            monitor: Monitor index to capture (0 = primary)
        """
        self._monitor = monitor
        self._sct = mss.mss()

    def capture(self) -> tuple[Image.Image, int, int]:
        """
        Capture a screenshot.

        Returns:
            Tuple of (PIL Image, original_width, original_height)
        """
        # Get monitor info
        monitors = self._sct.monitors
        if self._monitor < len(monitors):
            monitor = monitors[self._monitor + 1]  # monitors[0] is "all monitors"
        else:
            monitor = monitors[1]  # Default to primary

        # Capture screenshot
        sct_img = self._sct.grab(monitor)

        # Convert to PIL Image
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        return img, img.width, img.height

    def capture_scaled(self) -> tuple[str, int, int]:
        """
        Capture a screenshot and scale it to 1000x1000 for inference.

        Returns:
            Tuple of (base64_encoded_image, original_width, original_height)
        """
        img, original_width, original_height = self.capture()

        # Scale to inference size while maintaining aspect ratio
        scaled_img = self._scale_image(img, INFERENCE_SIZE)

        # Encode as base64
        buffer = io.BytesIO()
        scaled_img.save(buffer, format="PNG", optimize=True)
        base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return base64_data, original_width, original_height

    def _scale_image(
        self, img: Image.Image, target_size: tuple[int, int]
    ) -> Image.Image:
        """
        Scale image to target size while maintaining aspect ratio.
        Pads with black if needed.

        Args:
            img: Source PIL Image
            target_size: Target (width, height)

        Returns:
            Scaled PIL Image
        """
        target_w, target_h = target_size
        orig_w, orig_h = img.size

        # Calculate scale factor
        scale = min(target_w / orig_w, target_h / orig_h)

        # Calculate new size
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        # Resize with high-quality resampling
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Create target image with black background
        result = Image.new("RGB", target_size, (0, 0, 0))

        # Paste resized image centered
        offset_x = (target_w - new_w) // 2
        offset_y = (target_h - new_h) // 2
        result.paste(resized, (offset_x, offset_y))

        return result

    def close(self):
        """Close the screen capture resources"""
        self._sct.close()


def scale_coordinates_to_original(
    x: int,
    y: int,
    original_width: int,
    original_height: int,
    inference_size: tuple[int, int] = INFERENCE_SIZE,
) -> tuple[int, int]:
    """
    Scale coordinates from inference size back to original screen coordinates.

    Args:
        x: X coordinate in inference scale
        y: Y coordinate in inference scale
        original_width: Original screen width
        original_height: Original screen height
        inference_size: Size used for inference (default 1000x1000)

    Returns:
        Tuple of (scaled_x, scaled_y) in original coordinates
    """
    target_w, target_h = inference_size

    # Calculate the scale that was applied
    scale = min(target_w / original_width, target_h / original_height)

    # Calculate the offset (centering)
    new_w = int(original_width * scale)
    new_h = int(original_height * scale)
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2

    # Adjust for offset
    adjusted_x = x - offset_x
    adjusted_y = y - offset_y

    # Scale back to original
    original_x = int(adjusted_x / scale)
    original_y = int(adjusted_y / scale)

    # Clamp to valid range
    original_x = max(0, min(original_x, original_width - 1))
    original_y = max(0, min(original_y, original_height - 1))

    return original_x, original_y


def scale_action_coordinates(
    action: dict, original_width: int, original_height: int
) -> dict:
    """
    Scale all coordinates in an action from inference size to original size.

    Args:
        action: Action dictionary with coordinates in inference scale
        original_width: Original screen width
        original_height: Original screen height

    Returns:
        Action dictionary with coordinates in original scale
    """
    scaled_action = action.copy()

    # Scale single point coordinates
    if "x" in scaled_action and "y" in scaled_action:
        scaled_action["x"], scaled_action["y"] = scale_coordinates_to_original(
            scaled_action["x"],
            scaled_action["y"],
            original_width,
            original_height,
        )

    # Scale start/end coordinates for drag
    if "start_x" in scaled_action:
        scaled_action["start_x"], scaled_action["start_y"] = scale_coordinates_to_original(
            scaled_action["start_x"],
            scaled_action["start_y"],
            original_width,
            original_height,
        )
        scaled_action["end_x"], scaled_action["end_y"] = scale_coordinates_to_original(
            scaled_action["end_x"],
            scaled_action["end_y"],
            original_width,
            original_height,
        )

    return scaled_action
