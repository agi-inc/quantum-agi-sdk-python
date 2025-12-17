"""
State Machine Tests for Quantum AGI SDK

These tests verify that the AGIClient implements the state machine
described in the MANUAL.md correctly.

State Machine Overview:
- IDLE: Initial state
- RUNNING: Actively executing a task
- PAUSE: Paused by user
- WAITING_CONFIRMATION: Awaiting user confirmation
- WAITING_QUESTION_ANSWER: Awaiting user answer
- FINISH: Task completed (waiting for SendMessage or End)
- FAIL: Task failed

Key Transitions:
- IDLE -> RUNNING: via Start()
- RUNNING -> WAITING_CONFIRMATION: when confirmation needed
- WAITING_CONFIRMATION -> RUNNING: via Confirm(true/false)
- RUNNING -> WAITING_QUESTION_ANSWER: when question asked
- WAITING_QUESTION_ANSWER -> RUNNING: via Answer(text/null)
- RUNNING -> PAUSE: via Pause()
- PAUSE -> RUNNING: via Resume()
- RUNNING -> FINISH: when finish action received
- FINISH -> RUNNING: via SendMessage()
- FINISH -> exits: via End()
- RUNNING -> FAIL: when fail action received
- ANY -> FINISH: via EndSession()
"""

import pytest
from quantum_agi_sdk.models import (
    AgentState,
    AgentStatus,
    TaskResult,
    ConfirmationRequest,
    QuestionRequest,
)


class TestAgentStatusEnum:
    """Test that all required states exist in the enum"""

    def test_has_idle_state(self):
        assert hasattr(AgentStatus, 'IDLE')

    def test_has_running_state(self):
        assert hasattr(AgentStatus, 'RUNNING')

    def test_has_pause_state(self):
        assert hasattr(AgentStatus, 'PAUSE')

    def test_has_waiting_confirmation_state(self):
        assert hasattr(AgentStatus, 'WAITING_CONFIRMATION')

    def test_has_waiting_question_answer_state(self):
        assert hasattr(AgentStatus, 'WAITING_QUESTION_ANSWER')

    def test_has_finish_state(self):
        assert hasattr(AgentStatus, 'FINISH')

    def test_has_fail_state(self):
        assert hasattr(AgentStatus, 'FAIL')


class TestAgentState:
    """Test AgentState structure"""

    def test_default_state_is_idle(self):
        state = AgentState()
        assert state.status == AgentStatus.IDLE

    def test_state_has_required_fields(self):
        state = AgentState(
            status=AgentStatus.RUNNING,
            task="Test task",
            current_step=5,
            progress_message="Working...",
            error=None,
        )
        assert state.status == AgentStatus.RUNNING
        assert state.task == "Test task"
        assert state.current_step == 5
        assert state.progress_message == "Working..."
        assert state.error is None

    def test_state_with_error(self):
        state = AgentState(
            status=AgentStatus.FAIL,
            error="Something went wrong"
        )
        assert state.status == AgentStatus.FAIL
        assert state.error == "Something went wrong"


class TestTaskResult:
    """Test TaskResult structure"""

    def test_successful_result(self):
        result = TaskResult(
            success=True,
            message="Task completed",
            steps_taken=5,
            duration_seconds=10.5
        )
        assert result.success is True
        assert result.message == "Task completed"
        assert result.steps_taken == 5
        assert result.duration_seconds == 10.5

    def test_failed_result(self):
        result = TaskResult(
            success=False,
            message="Task failed: timeout",
            steps_taken=3,
            duration_seconds=30.0
        )
        assert result.success is False
        assert "failed" in result.message.lower()


class TestConfirmationRequest:
    """Test ConfirmationRequest structure"""

    def test_confirmation_request_fields(self):
        request = ConfirmationRequest(
            action_description="Delete important file?",
            pending_action={"type": "click", "x": 100, "y": 200},
            context={"step": 1, "task": "cleanup"}
        )
        assert request.action_description == "Delete important file?"
        assert request.pending_action["type"] == "click"
        assert request.context["step"] == 1


class TestQuestionRequest:
    """Test QuestionRequest structure"""

    def test_question_request_fields(self):
        request = QuestionRequest(
            question="What is your email?",
            context="Required for form submission"
        )
        assert request.question == "What is your email?"
        assert request.context == "Required for form submission"

    def test_question_request_optional_context(self):
        request = QuestionRequest(
            question="Yes or no?"
        )
        assert request.question == "Yes or no?"
        assert request.context is None


class TestClientStateMethods:
    """Test AGIClient state transition methods without running actual tasks"""

    @pytest.fixture
    def client(self):
        """Create a client for testing"""
        from quantum_agi_sdk.client import AGIClient
        return AGIClient()

    def test_initial_state_is_idle(self, client):
        """Client should start in IDLE state"""
        assert client.state.status == AgentStatus.IDLE
        assert client.state.current_step == 0

    def test_pause_when_not_running_has_no_effect(self, client):
        """Pause() when idle should have no effect"""
        states = []
        client._on_status_change = lambda s: states.append(s.status)

        client.pause()

        # Should still be idle
        assert client.state.status == AgentStatus.IDLE
        assert len(states) == 0

    def test_resume_when_not_running_has_no_effect(self, client):
        """Resume() when idle should have no effect"""
        states = []
        client._on_status_change = lambda s: states.append(s.status)

        client.resume()

        assert client.state.status == AgentStatus.IDLE
        assert len(states) == 0

    def test_confirm_when_no_pending_has_no_effect(self, client):
        """Confirm() when no pending confirmation should have no effect"""
        # Should not throw
        client.confirm(True)
        client.confirm(False)

        assert client.state.status == AgentStatus.IDLE

    def test_answer_when_no_pending_has_no_effect(self, client):
        """Answer() when no pending question should have no effect"""
        # Should not throw
        client.answer("test answer")
        client.answer(None)

        assert client.state.status == AgentStatus.IDLE

    def test_end_session_transitions_to_finish(self, client):
        """EndSession() should transition to FINISH state"""
        states = []
        client._on_status_change = lambda s: states.append(s.status)

        client.end_session()

        assert client.state.status == AgentStatus.FINISH
        assert AgentStatus.FINISH in states

    def test_send_message_adds_to_messages(self, client):
        """SendMessage() should add message to internal list"""
        initial_count = len(client._get_messages_copy())

        client.send_message("Test message")

        messages = client._get_messages_copy()
        assert len(messages) == initial_count + 1
        assert messages[-1]["role"] == "user"

    def test_end_does_not_throw(self, client):
        """End() should not throw when idle"""
        # Should not throw
        client.end()


class TestThreadSafeMessageMethods:
    """Test thread-safe message handling methods"""

    @pytest.fixture
    def client(self):
        from quantum_agi_sdk.client import AGIClient
        return AGIClient()

    def test_add_message(self, client):
        """_add_message should add to internal list"""
        client._add_message({"role": "user", "content": "test"})
        messages = client._get_messages_copy()
        assert len(messages) == 1
        assert messages[0]["content"] == "test"

    def test_get_messages_copy_returns_copy(self, client):
        """_get_messages_copy should return independent copy"""
        client._add_message({"role": "user", "content": "test"})

        copy1 = client._get_messages_copy()
        copy2 = client._get_messages_copy()

        assert copy1 == copy2
        assert copy1 is not copy2  # Different objects

        # Modifying copy shouldn't affect original
        copy1.append({"role": "assistant", "content": "response"})
        assert len(client._get_messages_copy()) == 1

    def test_trim_messages(self, client):
        """_trim_messages should keep only last N messages"""
        for i in range(10):
            client._add_message({"role": "user", "content": f"msg{i}"})

        assert len(client._get_messages_copy()) == 10

        client._trim_messages(5)

        messages = client._get_messages_copy()
        assert len(messages) == 5
        assert messages[0]["content"] == "msg5"  # Should keep last 5

    def test_clear_messages(self, client):
        """_clear_messages should remove all messages"""
        for i in range(5):
            client._add_message({"role": "user", "content": f"msg{i}"})

        assert len(client._get_messages_copy()) == 5

        client._clear_messages()

        assert len(client._get_messages_copy()) == 0


class TestStateTransitionCallbacks:
    """Test that state transitions trigger callbacks correctly"""

    @pytest.fixture
    def client(self):
        from quantum_agi_sdk.client import AGIClient
        return AGIClient()

    def test_status_change_callback_called(self, client):
        """Status change callback should be called on state changes"""
        states = []
        client._on_status_change = lambda s: states.append(s.status)

        # Force internal state update
        client._update_state(status=AgentStatus.RUNNING)
        client._update_state(status=AgentStatus.PAUSE)
        client._update_state(status=AgentStatus.FINISH)

        assert AgentStatus.RUNNING in states
        assert AgentStatus.PAUSE in states
        assert AgentStatus.FINISH in states

    def test_state_property_returns_current_state(self, client):
        """state property should return current state"""
        assert client.state.status == AgentStatus.IDLE

        client._update_state(status=AgentStatus.RUNNING, task="Test")

        assert client.state.status == AgentStatus.RUNNING
        assert client.state.task == "Test"
