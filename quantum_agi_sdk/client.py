"""
Main AGI Client - The primary SDK interface
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from typing import Callable, Optional

import httpx

from quantum_agi_sdk.capture import ScreenCapture
from quantum_agi_sdk.executor import ActionExecutor
from quantum_agi_sdk.models import (
    AgentState,
    AgentStatus,
    ConfirmationRequest,
    QuestionRequest,
    TaskResult,
    StartSessionRequest,
    StartSessionResponse,
    QuantumInferenceRequest,
    QuantumInferenceResponse,
    FinishSessionRequest,
    FinishSessionResponse,
)
from quantum_agi_sdk.telemetry import TelemetryManager


class AGIClient:
    """
    AGI Client

    This is the main interface for the Quantum AGI SDK. It handles:
    - Task orchestration
    - Screenshot capture
    - Cloud inference communication
    - Local action execution
    - Confirmation flow for high-impact actions
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        on_status_change: Optional[Callable[[AgentState], None]] = None,
        on_confirmation_required: Optional[Callable[[ConfirmationRequest], None]] = None,
        on_question_required: Optional[Callable[[QuestionRequest], None]] = None,
        on_action_executed: Optional[Callable[[dict], None]] = None,
        max_steps: int = 100,
        step_delay: float = 0.5,
    ):
        """
        Initialize the AGI Client.

        Args:
            api_key: API key for authentication
            on_status_change: Callback for agent status changes
            on_confirmation_required: Callback when user confirmation is needed
            on_question_required: Callback when agent asks a question requiring user input
            on_action_executed: Callback after each action is executed
            max_steps: Maximum steps before stopping
            step_delay: Delay between steps in seconds
        """
        self._api_url = (api_url or os.environ.get("AGI_API_URL") or "https://api.agi.tech").rstrip("/")
        self._api_key = api_key
        self._on_status_change = on_status_change
        self._on_confirmation_required = on_confirmation_required
        self._on_question_required = on_question_required
        self._on_action_executed = on_action_executed
        self._max_steps = max_steps
        self._step_delay = step_delay

        self._state = AgentState()
        self._capture = ScreenCapture()
        self._executor = ActionExecutor()
        self._http_client = httpx.AsyncClient(timeout=30.0)

        self._running = False
        self._paused = False
        self._pending_confirmation: Optional[ConfirmationRequest] = None
        self._confirmation_event = asyncio.Event()
        self._confirmed = False
        self._pending_question: Optional[QuestionRequest] = None
        self._question_event = asyncio.Event()
        self._answer: Optional[str] = None
        self._messages: list[dict] = []
        self._task_start_time: Optional[float] = None
        self._session_id: Optional[str] = None
        self._paused_for_finish = False
        self._finish_event = asyncio.Event()
        self._correlation_id: Optional[str] = None

        # Initialize telemetry - sends directly to Sentry
        self._telemetry = TelemetryManager()
        self._telemetry.initialize()

    @property
    def state(self) -> AgentState:
        """Get current agent state"""
        return self._state

    async def start(self, task: str, context: Optional[dict] = None) -> TaskResult:
        """
        Start executing a task.

        Args:
            task: The task/intent from Quantum
            context: Optional context

        Returns:
            TaskResult with success status and details
        """
        if self._running:
            raise RuntimeError("Agent is already running a task")

        self._running = True
        self._paused = False
        self._messages = []
        self._task_start_time = time.time()

        # Generate correlation ID for tracing
        self._correlation_id = f"qs-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Send real-time event for session start
        self._telemetry.capture_message(
            "[quantum.sdk] session_start",
            level="info",
            tags={
                "event_name": "session_start",
                "correlation_id": self._correlation_id,
            },
            extras={
                "task": task,
                "api_url": self._api_url,
                "max_steps": self._max_steps,
            },
        )

        self._update_state(
            status=AgentStatus.RUNNING,
            task=task,
            current_step=0,
            progress_message="Starting task...",
        )

        try:
            return await self._run_task_loop(task, context)
        except Exception as e:
            self._update_state(status=AgentStatus.FAIL, error=str(e))
            self._telemetry.capture_exception(e)
            return TaskResult(
                success=False,
                message=f"Task failed: {str(e)}",
                steps_taken=self._state.current_step,
                duration_seconds=time.time() - self._task_start_time,
            )
        finally:
            self._running = False

    async def _run_task_loop(self, task: str, context: Optional[dict]) -> TaskResult:
        """Main task execution loop"""
        try:
            session = await self._start_session(task, context)
            self._session_id = session.id
        except Exception as e:
            raise RuntimeError(f"Failed to start session: {e}")

        # Add initial task as user message
        self._messages.append({
            "role": "user",
            "content": [{"type": "text", "text": f"Task: {task}"}],
        })

        try:
            return await self._execute_task_loop(task, context)
        finally:
            await self._finish_session_safe()

    async def _execute_task_loop(self, task: str, context: Optional[dict]) -> TaskResult:
        """Execute the task loop after session is started"""
        step = 0
        while step < self._max_steps and self._running:
            while self._paused and self._running:
                await asyncio.sleep(0.1)

            if not self._running:
                break

            if self._pending_confirmation:
                self._update_state(
                    status=AgentStatus.WAITING_CONFIRMATION,
                    progress_message=f"Waiting for confirmation: {self._pending_confirmation.action_description}",
                )
                await self._confirmation_event.wait()
                self._confirmation_event.clear()

                if self._confirmed:
                    # User approved - insert confirmation message and execute action
                    self._messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": "User confirmed the action."}],
                    })
                    if self._pending_confirmation.pending_action:
                        await self._run_action(self._pending_confirmation.pending_action)
                else:
                    # User denied - insert denial message and let agent adapt
                    action_desc = self._pending_confirmation.action_description
                    self._messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": f"User denied the action: {action_desc}. Please try a different approach."}],
                    })

                self._pending_confirmation = None
                self._update_state(status=AgentStatus.RUNNING)
                continue

            if self._pending_question:
                self._update_state(
                    status=AgentStatus.WAITING_QUESTION_ANSWER,
                    progress_message=f"Waiting for answer: {self._pending_question.question}",
                )
                await self._question_event.wait()
                self._question_event.clear()

                if self._answer is not None:
                    # User provided answer - insert as user message
                    self._messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": f"User answer: {self._answer}"}],
                    })
                else:
                    # User declined to answer - insert decline message
                    self._messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": "User declined to answer. Please proceed without this information."}],
                    })

                self._pending_question = None
                self._answer = None
                self._update_state(status=AgentStatus.RUNNING)
                continue

            step += 1
            self._update_state(
                current_step=step,
                progress_message=f"Executing step {step}...",
            )

            # Capture screenshot and add as user message
            screenshot_b64 = self._capture.capture()

            # Add screenshot as user message
            self._messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                    },
                ],
            })

            # Keep only last ~20 messages to avoid context overflow
            if len(self._messages) > 20:
                self._messages = self._messages[-20:]

            # Get next action from cloud inference
            request = QuantumInferenceRequest(
                messages=list(self._messages),
            )

            response = await self._call_quantum_inference(request)
            action = response.action

            # Send real-time event for inference response
            self._telemetry.capture_message(
                "[quantum.sdk] http_response",
                level="info",
                tags={
                    "event_name": "http_response",
                    "correlation_id": self._correlation_id,
                    "session_id": self._session_id,
                },
                extras={
                    "step": step,
                    "action_type": action.get("type", "unknown"),
                    "confidence": response.confidence,
                    "requires_confirmation": response.requires_confirmation,
                    "reasoning": response.reasoning or "",
                },
            )

            # Check if confirmation is required
            if response.requires_confirmation or action.get("type") == "confirm":
                self._pending_confirmation = ConfirmationRequest(
                    action_description=action.get(
                        "action_description", response.reasoning or "Confirm this action?"
                    ),
                    pending_action=action.get("pending_action", action),
                    context={"step": step, "task": task},
                )
                if self._on_confirmation_required:
                    self._on_confirmation_required(self._pending_confirmation)
                continue

            # Check if a question is being asked
            if action.get("type") == "ask_question":
                self._pending_question = QuestionRequest(
                    question=action.get("question", "Please provide input"),
                    context=action.get("context"),
                )
                if self._on_question_required:
                    self._on_question_required(self._pending_question)
                continue

            # Check for task completion - enter paused state, don't return
            if action.get("type") == "finish":
                self._update_state(
                    status=AgentStatus.FINISH,
                    progress_message=action.get("message", "Task completed successfully"),
                )
                # Wait for user to either send_message() to continue or end() to truly finish
                self._paused_for_finish = True
                self._finish_event.clear()
                await self._finish_event.wait()
                self._paused_for_finish = False

                # If user called end() to finish, exit the loop
                if not self._running:
                    return TaskResult(
                        success=True,
                        message=action.get("message", "Task completed successfully"),
                        steps_taken=step,
                        duration_seconds=time.time() - self._task_start_time,
                    )
                # Otherwise, user added a message - continue the loop
                self._update_state(status=AgentStatus.RUNNING)
                continue

            # Check for failure
            if action.get("type") == "fail":
                self._update_state(
                    status=AgentStatus.FAIL,
                    error=action.get("reason", "Unknown error"),
                )
                return TaskResult(
                    success=False,
                    message=action.get("reason", "Task failed"),
                    steps_taken=step,
                    duration_seconds=time.time() - self._task_start_time,
                )

            # Execute the action
            await self._run_action(action)

            # Record action as assistant message with tool call
            self._messages.append({
                "role": "assistant",
                "content": response.reasoning or "",
                "tool_calls": [
                    {
                        "id": str(uuid.uuid4()),
                        "type": "function",
                        "function": {
                            "name": action.get("type", "unknown"),
                            "arguments": json.dumps(action),
                        },
                    },
                ],
            })

            await asyncio.sleep(self._step_delay)

        self._update_state(status=AgentStatus.FAIL, error="Maximum steps reached")
        return TaskResult(
            success=False,
            message="Maximum steps reached without completing task",
            steps_taken=step,
            duration_seconds=time.time() - self._task_start_time,
        )

    async def _run_action(self, action: dict):
        """Execute a single action"""
        self._update_state(last_action=action)
        self._executor.execute(action)
        if self._on_action_executed:
            self._on_action_executed(action)

    async def _start_session(self, task: str, context: Optional[dict]) -> StartSessionResponse:
        """Start a quantum agent session"""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = StartSessionRequest(task=task, context=context)
        response = await self._http_client.post(
            f"{self._api_url}/v1/quantum/sessions",
            json=request.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        return StartSessionResponse(**response.json())

    async def _call_quantum_inference(self, request: QuantumInferenceRequest) -> QuantumInferenceResponse:
        """Call the quantum inference endpoint"""
        if not self._session_id:
            raise RuntimeError("No active session")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = await self._http_client.post(
            f"{self._api_url}/v1/quantum/sessions/{self._session_id}/inference",
            json=request.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        return QuantumInferenceResponse(**response.json())

    async def _finish_session(self, reason: Optional[str] = None) -> FinishSessionResponse:
        """Finish the current session successfully"""
        if not self._session_id:
            raise RuntimeError("No active session")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = FinishSessionRequest(reason=reason)
        response = await self._http_client.post(
            f"{self._api_url}/v1/quantum/sessions/{self._session_id}/finish",
            json=request.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        self._session_id = None
        return FinishSessionResponse(**response.json())

    async def _fail_session(self, reason: Optional[str] = None) -> FinishSessionResponse:
        """Fail the current session"""
        if not self._session_id:
            raise RuntimeError("No active session")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = FinishSessionRequest(reason=reason)
        response = await self._http_client.post(
            f"{self._api_url}/v1/quantum/sessions/{self._session_id}/fail",
            json=request.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        self._session_id = None
        return FinishSessionResponse(**response.json())

    async def _finish_session_safe(self):
        """Safely finish the session, ignoring errors"""
        if not self._session_id:
            return
        try:
            if self._state.status == AgentStatus.FAIL:
                await self._fail_session()
            else:
                await self._finish_session()
        except Exception:
            pass

    def send_message(self, message: str):
        """Send a user message to the agent.

        This can be used to provide additional context or instructions.
        If the agent is paused after a finish action, this will resume execution.
        """
        self._messages.append({
            "role": "user",
            "content": [{"type": "text", "text": message}],
        })
        # Resume loop if paused after finish
        if self._paused_for_finish:
            self._update_state(status=AgentStatus.RUNNING)
            self._finish_event.set()

    def end(self):
        """Explicitly end the session.

        Use this when you want to truly finish after the agent has completed
        and entered the paused-for-finish state.
        """
        self._running = False
        self._paused_for_finish = False
        self._finish_event.set()

    def pause(self):
        """Pause the agent execution."""
        if not self._running:
            return
        self._paused = True
        self._update_state(status=AgentStatus.PAUSE, progress_message="Agent paused")

    def resume(self):
        """Resume a paused agent"""
        if not self._running:
            return
        self._paused = False
        self._update_state(status=AgentStatus.RUNNING, progress_message="Agent resumed")

    def end_session(self):
        """End the agent session completely."""
        self._running = False
        self._paused = False
        self._paused_for_finish = False
        self._update_state(status=AgentStatus.FINISH, progress_message="Session ended by user")
        self._confirmed = False
        self._confirmation_event.set()
        self._answer = None
        self._question_event.set()
        self._finish_event.set()

    def confirm(self, approved: bool = True):
        """Respond to a confirmation request."""
        if not self._pending_confirmation:
            return
        self._confirmed = approved
        self._confirmation_event.set()

    def answer(self, user_answer: Optional[str]):
        """Submit an answer to a question from the agent.

        Pass None as answer to decline answering (agent will continue without it).
        """
        if not self._pending_question:
            return
        self._answer = user_answer
        self._question_event.set()

    def _update_state(self, **kwargs):
        """Update agent state and notify listeners"""
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
        if self._on_status_change:
            self._on_status_change(self._state)

    async def close(self):
        """Clean up resources"""
        await self._http_client.aclose()
        self._capture.close()
        self._telemetry.flush()
        self._telemetry.close()


class AGIClientSync:
    """Synchronous wrapper for AGIClient"""

    def __init__(self, *args, **kwargs):
        self._async_client = AGIClient(*args, **kwargs)
        self._loop = asyncio.new_event_loop()

    def start(self, task: str, context: Optional[dict] = None) -> TaskResult:
        return self._loop.run_until_complete(self._async_client.start(task, context))

    def pause(self):
        self._async_client.pause()

    def resume(self):
        self._async_client.resume()

    def end_session(self):
        self._async_client.end_session()

    def confirm(self, approved: bool = True):
        self._async_client.confirm(approved)

    def answer(self, user_answer: Optional[str]):
        self._async_client.answer(user_answer)

    def send_message(self, message: str):
        self._async_client.send_message(message)

    def end(self):
        self._async_client.end()

    @property
    def state(self) -> AgentState:
        return self._async_client.state

    def close(self):
        self._loop.run_until_complete(self._async_client.close())
        self._loop.close()
