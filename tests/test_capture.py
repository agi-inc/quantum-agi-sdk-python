"""Tests for screenshot capture and coordinate scaling"""

import pytest
from quantum_agi_sdk.capture import (
    scale_coordinates_to_original,
    scale_action_coordinates,
    INFERENCE_SIZE,
)


class TestCoordinateScaling:
    """Test coordinate scaling functions"""

    def test_scale_coordinates_center(self):
        """Test scaling coordinates from center of image"""
        # For a 1920x1080 screen scaled to 1000x1000
        # Scale factor is min(1000/1920, 1000/1080) = 0.5208...
        # Actual scaled size would be ~1000x562
        # Centered vertically with offset_y = (1000-562)//2 = 219

        original_width = 1920
        original_height = 1080

        # Center of scaled image
        x, y = 500, 500

        result_x, result_y = scale_coordinates_to_original(
            x, y, original_width, original_height
        )

        # Should map back to approximately center of original
        assert 900 < result_x < 1020
        assert 400 < result_y < 680

    def test_scale_coordinates_corner(self):
        """Test scaling coordinates from corner"""
        original_width = 1920
        original_height = 1080

        # Top-left of the actual content (accounting for letterboxing)
        # With 1920x1080 -> 1000x1000, the image is letterboxed
        scale = min(1000 / 1920, 1000 / 1080)
        new_h = int(1080 * scale)
        offset_y = (1000 - new_h) // 2

        x, y = 0, offset_y  # Top-left of actual content

        result_x, result_y = scale_coordinates_to_original(
            x, y, original_width, original_height
        )

        assert result_x == 0
        assert result_y == 0

    def test_scale_action_coordinates_click(self):
        """Test scaling a click action"""
        action = {
            "type": "click",
            "x": 500,
            "y": 500,
        }

        scaled = scale_action_coordinates(action, 1920, 1080)

        assert scaled["type"] == "click"
        assert "x" in scaled
        assert "y" in scaled
        assert isinstance(scaled["x"], int)
        assert isinstance(scaled["y"], int)

    def test_scale_action_coordinates_drag(self):
        """Test scaling a drag action"""
        action = {
            "type": "drag",
            "start_x": 100,
            "start_y": 300,
            "end_x": 900,
            "end_y": 700,
        }

        scaled = scale_action_coordinates(action, 1920, 1080)

        assert scaled["type"] == "drag"
        assert "start_x" in scaled
        assert "start_y" in scaled
        assert "end_x" in scaled
        assert "end_y" in scaled

    def test_scale_action_coordinates_type(self):
        """Test that non-coordinate actions pass through unchanged"""
        action = {
            "type": "type",
            "text": "Hello world",
        }

        scaled = scale_action_coordinates(action, 1920, 1080)

        assert scaled == action

    def test_coordinates_clamped_to_bounds(self):
        """Test that coordinates are clamped to valid range"""
        # Coordinates outside the image content area
        x, y = 0, 0  # Before offset

        result_x, result_y = scale_coordinates_to_original(
            x, y, 1920, 1080
        )

        # Should be clamped to valid range
        assert result_x >= 0
        assert result_y >= 0
        assert result_x < 1920
        assert result_y < 1080
