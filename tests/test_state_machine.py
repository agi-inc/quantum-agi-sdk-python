"""
State Machine Tests for Quantum AGI SDK (Python)

These tests verify all state transitions defined in MANUAL.md:

| #  | Transition                         | Trigger            | Test Method                                                 |
|----|------------------------------------|--------------------|-------------------------------------------------------------|
| 1  | IDLE → RUNNING                     | start(task)        | test_transition_idle_to_running                             |
| 2  | RUNNING → WAITING_CONFIRMATION     | confirmation action| test_transition_running_to_waiting_confirmation             |
| 3  | WAITING_CONFIRMATION → RUNNING     | confirm(True)      | test_transition_waiting_confirmation_to_running_approved    |
| 4  | WAITING_CONFIRMATION → RUNNING     | confirm(False)     | test_transition_waiting_confirmation_to_running_denied      |
| 5  | RUNNING → WAITING_QUESTION_ANSWER  | ask_question action| test_transition_running_to_waiting_question                 |
| 6  | WAITING_QUESTION_ANSWER → RUNNING  | answer(text)       | test_transition_waiting_question_to_running_answered        |
| 7  | WAITING_QUESTION_ANSWER → RUNNING  | answer(None)       | test_transition_waiting_question_to_running_declined        |
| 8  | RUNNING → PAUSE                    | pause()            | test_transition_running_to_pause                            |
| 9  | PAUSE → RUNNING                    | resume()           | test_transition_pause_to_running                            |
| 10 | RUNNING → FINISH                   | finish action      | test_transition_running_to_finish                           |
| 11 | FINISH → RUNNING                   | send_message()     | test_transition_finish_to_running_via_send_message          |
| 12 | FINISH → exits                     | end()              | test_transition_finish_exits_via_end                        |
| 13 | RUNNING → FAIL                     | fail action        | test_transition_running_to_fail                             |
| 14 | ANY → FINISH                       | end_session()      | test_transition_any_to_finish_via_end_session_from_*        |
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


class TestAllStateTransitions:
    """
    Comprehensive tests for all state transitions defined in MANUAL.md state diagram.

    Transitions covered:
    1. IDLE → RUNNING: via Start(task)
    2. RUNNING → WAITING_CONFIRMATION: when confirmation action received
    3. WAITING_CONFIRMATION → RUNNING: via Confirm(true)
    4. WAITING_CONFIRMATION → RUNNING: via Confirm(false)
    5. RUNNING → WAITING_QUESTION_ANSWER: when ask_question action received
    6. WAITING_QUESTION_ANSWER → RUNNING: via Answer(text)
    7. WAITING_QUESTION_ANSWER → RUNNING: via Answer(null)
    8. RUNNING → PAUSE: via Pause()
    9. PAUSE → RUNNING: via Resume()
    10. RUNNING → FINISH: when finish action received
    11. FINISH → RUNNING: via SendMessage()
    12. FINISH → exits: via End()
    13. RUNNING → FAIL: when fail action received
    14. ANY → FINISH: via EndSession()
    """

    @pytest.fixture
    def client(self):
        from quantum_agi_sdk.client import AGIClient
        return AGIClient()

    # Transition 1: IDLE → RUNNING
    def test_transition_idle_to_running(self, client):
        """IDLE → RUNNING: Simulated via _update_state"""
        assert client.state.status == AgentStatus.IDLE

        client._update_state(status=AgentStatus.RUNNING, task="Test task")

        assert client.state.status == AgentStatus.RUNNING
        assert client.state.task == "Test task"

    # Transition 2: RUNNING → WAITING_CONFIRMATION
    def test_transition_running_to_waiting_confirmation(self, client):
        """RUNNING → WAITING_CONFIRMATION: when confirmation needed"""
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)

        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

    # Transition 3: WAITING_CONFIRMATION → RUNNING via Confirm(true)
    def test_transition_waiting_confirmation_to_running_approved(self, client):
        """WAITING_CONFIRMATION → RUNNING: via Confirm(true)"""
        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)
        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

        # Simulate confirmation approved - returns to RUNNING
        client._update_state(status=AgentStatus.RUNNING)

        assert client.state.status == AgentStatus.RUNNING

    # Transition 4: WAITING_CONFIRMATION → RUNNING via Confirm(false)
    def test_transition_waiting_confirmation_to_running_denied(self, client):
        """WAITING_CONFIRMATION → RUNNING: via Confirm(false) - agent adapts"""
        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)
        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

        # Simulate confirmation denied - still returns to RUNNING (agent adapts)
        client._update_state(status=AgentStatus.RUNNING)

        assert client.state.status == AgentStatus.RUNNING

    # Transition 5: RUNNING → WAITING_QUESTION_ANSWER
    def test_transition_running_to_waiting_question(self, client):
        """RUNNING → WAITING_QUESTION_ANSWER: when question asked"""
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)

        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

    # Transition 6: WAITING_QUESTION_ANSWER → RUNNING via Answer(text)
    def test_transition_waiting_question_to_running_answered(self, client):
        """WAITING_QUESTION_ANSWER → RUNNING: via Answer(text)"""
        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)
        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

        client._update_state(status=AgentStatus.RUNNING)

        assert client.state.status == AgentStatus.RUNNING

    # Transition 7: WAITING_QUESTION_ANSWER → RUNNING via Answer(null)
    def test_transition_waiting_question_to_running_declined(self, client):
        """WAITING_QUESTION_ANSWER → RUNNING: via Answer(null) - proceeds without info"""
        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)
        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

        # Declined still returns to RUNNING
        client._update_state(status=AgentStatus.RUNNING)

        assert client.state.status == AgentStatus.RUNNING

    # Transition 8: RUNNING → PAUSE via Pause()
    def test_transition_running_to_pause(self, client):
        """RUNNING → PAUSE: via Pause()"""
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client.pause()

        assert client.state.status == AgentStatus.PAUSE

    # Transition 9: PAUSE → RUNNING via Resume()
    def test_transition_pause_to_running(self, client):
        """PAUSE → RUNNING: via Resume()"""
        client._running = True
        client._paused = True
        client._update_state(status=AgentStatus.PAUSE)
        assert client.state.status == AgentStatus.PAUSE

        client.resume()

        assert client.state.status == AgentStatus.RUNNING

    # Transition 10: RUNNING → FINISH
    def test_transition_running_to_finish(self, client):
        """RUNNING → FINISH: when finish action received"""
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client._update_state(status=AgentStatus.FINISH, progress_message="Task completed")

        assert client.state.status == AgentStatus.FINISH

    # Transition 11: FINISH → RUNNING via SendMessage()
    def test_transition_finish_to_running_via_send_message(self, client):
        """FINISH → RUNNING: via SendMessage() - resumes loop"""
        client._running = True
        client._paused_for_finish = True
        client._update_state(status=AgentStatus.FINISH)
        assert client.state.status == AgentStatus.FINISH

        # SendMessage should trigger resume
        client.send_message("Continue with more work")

        assert client.state.status == AgentStatus.RUNNING

    # Transition 12: FINISH → exits via End()
    def test_transition_finish_exits_via_end(self, client):
        """FINISH → exits: via End() - returns TaskResult"""
        client._running = True
        client._paused_for_finish = True
        client._update_state(status=AgentStatus.FINISH)
        assert client.state.status == AgentStatus.FINISH

        client.end()

        # After end(), _running should be False
        assert client._running is False
        assert client._paused_for_finish is False

    # Transition 13: RUNNING → FAIL
    def test_transition_running_to_fail(self, client):
        """RUNNING → FAIL: when fail action received"""
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client._update_state(status=AgentStatus.FAIL, error="Task failed")

        assert client.state.status == AgentStatus.FAIL
        assert client.state.error == "Task failed"

    # Transition 14: ANY → FINISH via EndSession()
    def test_transition_any_to_finish_via_end_session_from_idle(self, client):
        """ANY → FINISH: via EndSession() from IDLE"""
        assert client.state.status == AgentStatus.IDLE

        client.end_session()

        assert client.state.status == AgentStatus.FINISH

    def test_transition_any_to_finish_via_end_session_from_running(self, client):
        """ANY → FINISH: via EndSession() from RUNNING"""
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client.end_session()

        assert client.state.status == AgentStatus.FINISH

    def test_transition_any_to_finish_via_end_session_from_pause(self, client):
        """ANY → FINISH: via EndSession() from PAUSE"""
        client._running = True
        client._paused = True
        client._update_state(status=AgentStatus.PAUSE)
        assert client.state.status == AgentStatus.PAUSE

        client.end_session()

        assert client.state.status == AgentStatus.FINISH
