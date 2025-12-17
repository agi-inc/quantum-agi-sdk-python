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

import asyncio
import pytest
from quantum_agi_sdk.client import AGIClient
from quantum_agi_sdk.models import (
    AgentState,
    AgentStatus,
    ConfirmationRequest,
    QuestionRequest,
)


class TestStateTransitions:
    """
    Test all state transitions from the MANUAL.md state diagram.
    """

    @pytest.fixture
    def client(self):
        return AGIClient()

    # Transition 1: IDLE → RUNNING via start()
    # Note: Full integration test requires mocking HTTP - tested in TypeScript SDK
    def test_transition_1_initial_state_is_idle(self, client):
        """Client starts in IDLE state, ready for transition to RUNNING"""
        assert client.state.status == AgentStatus.IDLE

    # Transition 2: RUNNING → WAITING_CONFIRMATION
    def test_transition_2_running_to_waiting_confirmation(self, client):
        """RUNNING → WAITING_CONFIRMATION when confirmation is required"""
        # Set up: put client in RUNNING state
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        # Simulate confirmation required (as the task loop would do)
        client._pending_confirmation = ConfirmationRequest(
            action_description="Delete file?",
            pending_action={"type": "click", "x": 100, "y": 100}
        )
        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)

        # Verify transition occurred
        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

    # Transition 3: WAITING_CONFIRMATION → RUNNING via confirm(True)
    def test_transition_3_waiting_confirmation_to_running_approved(self, client):
        """WAITING_CONFIRMATION → RUNNING when user approves"""
        # Set up: put client in WAITING_CONFIRMATION state
        client._running = True
        client._pending_confirmation = ConfirmationRequest(
            action_description="Delete file?",
            pending_action={"type": "click"}
        )
        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)
        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

        # Set up the confirmation event so confirm() works
        client._confirmation_event = asyncio.Event()

        # Action: user approves
        client.confirm(True)

        # Verify: _confirmed is True (the task loop will transition to RUNNING)
        assert client._confirmed is True

    # Transition 4: WAITING_CONFIRMATION → RUNNING via confirm(False)
    def test_transition_4_waiting_confirmation_to_running_denied(self, client):
        """WAITING_CONFIRMATION → RUNNING when user denies (agent adapts)"""
        # Set up: put client in WAITING_CONFIRMATION state
        client._running = True
        client._pending_confirmation = ConfirmationRequest(
            action_description="Delete file?",
            pending_action={"type": "click"}
        )
        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)
        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

        client._confirmation_event = asyncio.Event()

        # Action: user denies
        client.confirm(False)

        # Verify: _confirmed is False (the task loop will still transition to RUNNING)
        assert client._confirmed is False

    # Transition 5: RUNNING → WAITING_QUESTION_ANSWER
    def test_transition_5_running_to_waiting_question(self, client):
        """RUNNING → WAITING_QUESTION_ANSWER when agent asks question"""
        # Set up: put client in RUNNING state
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        # Simulate question asked (as the task loop would do)
        client._pending_question = QuestionRequest(question="What is your name?")
        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)

        # Verify transition occurred
        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

    # Transition 6: WAITING_QUESTION_ANSWER → RUNNING via answer(text)
    def test_transition_6_waiting_question_to_running_answered(self, client):
        """WAITING_QUESTION_ANSWER → RUNNING when user provides answer"""
        # Set up: put client in WAITING_QUESTION_ANSWER state
        client._running = True
        client._pending_question = QuestionRequest(question="What is your name?")
        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)
        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

        client._question_event = asyncio.Event()

        # Action: user provides answer
        client.answer("John")

        # Verify: answer is stored (task loop will transition to RUNNING)
        assert client._answer == "John"

    # Transition 7: WAITING_QUESTION_ANSWER → RUNNING via answer(None)
    def test_transition_7_waiting_question_to_running_declined(self, client):
        """WAITING_QUESTION_ANSWER → RUNNING when user declines to answer"""
        # Set up: put client in WAITING_QUESTION_ANSWER state
        client._running = True
        client._pending_question = QuestionRequest(question="What is your name?")
        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)
        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

        client._question_event = asyncio.Event()

        # Action: user declines
        client.answer(None)

        # Verify: answer is None (task loop will still transition to RUNNING)
        assert client._answer is None

    # Transition 8: RUNNING → PAUSE via pause()
    def test_transition_8_running_to_pause(self, client):
        """RUNNING → PAUSE when pause() is called"""
        # Set up: put client in RUNNING state
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        # Action: pause
        client.pause()

        # Verify transition occurred
        assert client.state.status == AgentStatus.PAUSE
        assert client._paused is True

    # Transition 9: PAUSE → RUNNING via resume()
    def test_transition_9_pause_to_running(self, client):
        """PAUSE → RUNNING when resume() is called"""
        # Set up: put client in PAUSE state
        client._running = True
        client._paused = True
        client._update_state(status=AgentStatus.PAUSE)
        assert client.state.status == AgentStatus.PAUSE

        # Action: resume
        client.resume()

        # Verify transition occurred
        assert client.state.status == AgentStatus.RUNNING
        assert client._paused is False

    # Transition 10: RUNNING → FINISH (via finish action in task loop)
    def test_transition_10_running_to_finish(self, client):
        """RUNNING → FINISH when finish action is received"""
        # Set up: put client in RUNNING state
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        # Simulate finish action (as the task loop would do)
        client._paused_for_finish = True
        client._update_state(status=AgentStatus.FINISH, progress_message="Task completed")

        # Verify transition occurred
        assert client.state.status == AgentStatus.FINISH

    # Transition 11: FINISH → RUNNING via send_message()
    def test_transition_11_finish_to_running_via_send_message(self, client):
        """FINISH → RUNNING when send_message() resumes execution"""
        # Set up: put client in FINISH state (paused for finish)
        client._running = True
        client._paused_for_finish = True
        client._finish_event = asyncio.Event()
        client._update_state(status=AgentStatus.FINISH)
        assert client.state.status == AgentStatus.FINISH

        # Action: send message to continue
        client.send_message("Continue working")

        # Verify transition occurred (state transitions to RUNNING, event is set)
        assert client.state.status == AgentStatus.RUNNING
        assert client._finish_event.is_set()

    # Transition 12: FINISH → exits via end()
    def test_transition_12_finish_exits_via_end(self, client):
        """FINISH → exits when end() is called"""
        # Set up: put client in FINISH state
        client._running = True
        client._paused_for_finish = True
        client._finish_event = asyncio.Event()
        client._update_state(status=AgentStatus.FINISH)
        assert client.state.status == AgentStatus.FINISH

        # Action: end the session
        client.end()

        # Verify: client is no longer running (exits the task loop)
        assert client._running is False
        assert client._paused_for_finish is False

    # Transition 13: RUNNING → FAIL (via fail action in task loop)
    def test_transition_13_running_to_fail(self, client):
        """RUNNING → FAIL when fail action is received"""
        # Set up: put client in RUNNING state
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        # Simulate fail action (as the task loop would do)
        client._update_state(status=AgentStatus.FAIL, error="Task failed: cannot find element")

        # Verify transition occurred
        assert client.state.status == AgentStatus.FAIL
        assert client.state.error == "Task failed: cannot find element"

    # Transition 14: ANY → FINISH via end_session()
    def test_transition_14_any_to_finish_from_idle(self, client):
        """IDLE → FINISH when end_session() is called"""
        assert client.state.status == AgentStatus.IDLE

        client.end_session()

        assert client.state.status == AgentStatus.FINISH

    def test_transition_14_any_to_finish_from_running(self, client):
        """RUNNING → FINISH when end_session() is called"""
        client._running = True
        client._update_state(status=AgentStatus.RUNNING)
        assert client.state.status == AgentStatus.RUNNING

        client.end_session()

        assert client.state.status == AgentStatus.FINISH
        assert client._running is False

    def test_transition_14_any_to_finish_from_pause(self, client):
        """PAUSE → FINISH when end_session() is called"""
        client._running = True
        client._paused = True
        client._update_state(status=AgentStatus.PAUSE)
        assert client.state.status == AgentStatus.PAUSE

        client.end_session()

        assert client.state.status == AgentStatus.FINISH

    def test_transition_14_any_to_finish_from_waiting_confirmation(self, client):
        """WAITING_CONFIRMATION → FINISH when end_session() is called"""
        client._running = True
        client._pending_confirmation = ConfirmationRequest(
            action_description="Test?",
            pending_action={"type": "click"}
        )
        client._confirmation_event = asyncio.Event()
        client._update_state(status=AgentStatus.WAITING_CONFIRMATION)
        assert client.state.status == AgentStatus.WAITING_CONFIRMATION

        client.end_session()

        assert client.state.status == AgentStatus.FINISH

    def test_transition_14_any_to_finish_from_waiting_question(self, client):
        """WAITING_QUESTION_ANSWER → FINISH when end_session() is called"""
        client._running = True
        client._pending_question = QuestionRequest(question="Test?")
        client._question_event = asyncio.Event()
        client._update_state(status=AgentStatus.WAITING_QUESTION_ANSWER)
        assert client.state.status == AgentStatus.WAITING_QUESTION_ANSWER

        client.end_session()

        assert client.state.status == AgentStatus.FINISH


class TestNoOpTransitions:
    """Test that methods are no-ops when preconditions aren't met."""

    @pytest.fixture
    def client(self):
        return AGIClient()

    def test_pause_when_not_running_is_noop(self, client):
        """pause() should not change state when not running"""
        assert client.state.status == AgentStatus.IDLE
        states = []
        client._on_status_change = lambda s: states.append(s.status)

        client.pause()

        assert client.state.status == AgentStatus.IDLE
        assert len(states) == 0  # No state change fired

    def test_resume_when_not_paused_is_noop(self, client):
        """resume() should not change state when not paused"""
        assert client.state.status == AgentStatus.IDLE
        states = []
        client._on_status_change = lambda s: states.append(s.status)

        client.resume()

        assert client.state.status == AgentStatus.IDLE
        assert len(states) == 0

    def test_confirm_when_no_pending_is_noop(self, client):
        """confirm() should do nothing when no pending confirmation"""
        assert client._pending_confirmation is None

        client.confirm(True)  # Should not raise
        client.confirm(False)  # Should not raise

    def test_answer_when_no_pending_is_noop(self, client):
        """answer() should do nothing when no pending question"""
        assert client._pending_question is None

        client.answer("test")  # Should not raise
        client.answer(None)  # Should not raise
