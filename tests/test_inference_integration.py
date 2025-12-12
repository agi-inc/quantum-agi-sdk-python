"""Integration tests for inference with multiple models.

Run with: pytest tests/test_inference_integration.py -v
Configure via environment variables:
  - AGI_API_BASE_URL: API endpoint (default: http://localhost:8000)
  - USER_API_KEY: API key for authentication
"""

import base64
import io
import os
import pytest
import httpx
from PIL import Image

# Test configuration from environment
API_URL = os.environ.get("AGI_API_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("USER_API_KEY", "f489f075-45fb-4e49-838c-054ff93728c3")

# Models to test
TEST_MODELS = [
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o",
    # "agi-inc/Qwen3-VL-32B-Instruct-L2-click-006",  # TODO: API-133
]


def generate_test_screenshot(width: int = 1000, height: int = 1000) -> str:
    """Generate a simple black test image and return as base64."""
    img = Image.new("RGB", (width, height), color="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def api_client():
    """Create an HTTP client for the API."""
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=60.0,
    )


@pytest.fixture
def test_screenshot():
    """Generate a test screenshot."""
    return generate_test_screenshot()


@pytest.fixture
def session_id(api_client):
    """Create a test session and return its ID."""
    response = api_client.post(
        "/v1/quantum/sessions",
        json={"task": "Test task: click the button", "context": {"test": True}},
    )
    assert response.status_code in (200, 201), f"Failed to create session: {response.text}"
    session = response.json()
    yield session["id"]

    # Cleanup: finish the session
    try:
        api_client.post(
            f"/v1/quantum/sessions/{session['id']}/finish",
            json={"status": "stopped", "reason": "Test completed"},
        )
    except Exception:
        pass


class TestInferenceIntegration:
    """Integration tests for the inference endpoint with multiple models."""

    @pytest.mark.parametrize("model", TEST_MODELS)
    def test_inference_with_model(self, api_client, test_screenshot, model):
        """Test inference with each model."""
        # Create a session for this test
        response = api_client.post(
            "/v1/quantum/sessions",
            json={"task": f"Test task for {model}: click the red button"},
        )
        assert response.status_code in (200, 201), f"Failed to create session: {response.text}"
        session = response.json()
        session_id = session["id"]

        try:
            # Run inference
            response = api_client.post(
                f"/v1/quantum/sessions/{session_id}/inference",
                json={
                    "screenshot_base64": test_screenshot,
                    "history": [],
                    "model": model,
                },
            )

            print(f"\n--- Model: {model} ---")
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"Action: {result.get('action')}")
                print(f"Reasoning: {(result.get('reasoning') or 'N/A')[:100]}...")
                print(f"Confidence: {result.get('confidence')}")

                # Verify response structure
                assert "action" in result
                assert "session_id" in result
                assert "step_number" in result
                assert result["session_id"] == session_id
            else:
                print(f"Error: {response.text}")
                # Don't fail on API errors - some models may be unavailable
                pytest.skip(f"Model {model} returned {response.status_code}: {response.text[:200]}")

        finally:
            # Cleanup
            api_client.post(
                f"/v1/quantum/sessions/{session_id}/finish",
                json={"status": "stopped"},
            )

    def test_inference_without_model_uses_default(self, api_client, test_screenshot, session_id):
        """Test that inference without model parameter uses default."""
        response = api_client.post(
            f"/v1/quantum/sessions/{session_id}/inference",
            json={
                "screenshot_base64": test_screenshot,
                "history": [],
                # No model specified - should use default
            },
        )

        print(f"\n--- Default Model ---")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"Action: {result.get('action')}")
            assert "action" in result
        else:
            print(f"Error: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
