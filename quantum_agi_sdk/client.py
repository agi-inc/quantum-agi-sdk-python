"""
Main AGI Client - The primary SDK interface
"""

import asyncio
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
    GetActionRequest,
    GetActionResponse,
    parse_action_string,
)
from quantum_agi_sdk.telemetry import TelemetryManager


class AGIClient:
    """
    AGI Client

    This is the main interface for the Quantum AGI SDK. It handles:
    - Task orchestration
    - Screenshot capture
    - Cloud inference communication (via /get_action)
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
        agent_type: str = "agi-0",
        platform: str = "desktop",
        run_type: str = "user_traffic",
        user_id: Optional[str] = None,
    ):
        """
        Initialize the AGI Client.

        Args:
            api_url: API URL (default: https://agi-inc--quantum-agi-cloud-dev-web.modal.run)
            api_key: API key for authentication (optional)
            on_status_change: Callback for agent status changes
            on_confirmation_required: Callback when user confirmation is needed
            on_question_required: Callback when agent asks a question requiring user input
            on_action_executed: Callback after each action is executed
            max_steps: Maximum steps before stopping
            step_delay: Delay between steps in seconds
            agent_type: Agent type: "agi-0" or "agi-1-preview" (default: agi-0)
            platform: Platform identifier (default: desktop)
            run_type: Run type (default: user_traffic)
            user_id: User ID for tracking (optional)
        """
        self._api_url = (api_url or os.environ.get("AGI_API_URL") or "https://agi-inc--quantum-agi-cloud-dev-web.modal.run").rstrip("/")
        self._api_key = api_key
        self._on_status_change = on_status_change
        self._on_confirmation_required = on_confirmation_required
        self._on_question_required = on_question_required
        self._on_action_executed = on_action_executed
        self._max_steps = max_steps
        self._step_delay = step_delay
        self._agent_type = agent_type
        self._platform = platform
        self._run_type = run_type
        self._user_id = user_id

        self._state = AgentState()
        self._capture = ScreenCapture()
        self._executor = ActionExecutor()
        self._http_client = httpx.AsyncClient(timeout=60.0)

        self._running = False
        self._paused = False
        self._pending_confirmation: Optional[ConfirmationRequest] = None
        self._confirmation_event = asyncio.Event()
        self._confirmed = False
        self._pending_question: Optional[QuestionRequest] = None
        self._question_event = asyncio.Event()
        self._answer: Optional[str] = None
        self._task_start_time: Optional[float] = None
        self._session_id: Optional[str] = None
        self._paused_for_finish = False
        self._finish_event = asyncio.Event()
        self._current_prompt: Optional[str] = None

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
            task: The task/intent for the agent
            context: Optional context

        Returns:
            TaskResult with success status and details
        """
        if self._running:
            raise RuntimeError("Agent is already running a task")

        self._running = True
        self._paused = False
        self._task_start_time = time.time()
        self._current_prompt = task

        # Generate session ID for this run
        self._session_id = f"sdk-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Send real-time event for session start
        self._telemetry.capture_message(
            "[quantum.sdk] session_start",
            level="info",
            tags={
                "event_name": "session_start",
                "session_id": self._session_id,
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

                if self._confirmed and self._pending_confirmation.pending_action:
                    await self._run_action(self._pending_confirmation.pending_action)

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

                # Update prompt with user answer if provided
                if self._answer is not None:
                    self._current_prompt = f"{task}\n\nUser answer to '{self._pending_question.question}': {self._answer}"

                self._pending_question = None
                self._answer = None
                self._update_state(status=AgentStatus.RUNNING)
                continue

            step += 1
            self._update_state(
                current_step=step,
                progress_message=f"Executing step {step}...",
            )

            # Start agent.step transaction for this step
            step_transaction = self._telemetry.start_transaction(
                name=f"agent.step.{step}",
                operation="agent.step",
                tags={
                    "session_id": self._session_id or "",
                    "step": str(step),
                },
            )

            step_status = "ok"

            try:
                # Capture screenshot with span tracking
                screenshot_span = self._telemetry.start_span(
                    operation="screenshot.capture",
                    description="Capture screenshot",
                    parent_span=step_transaction,
                )
                try:
                    screenshot_b64 = self._capture.capture()
                    self._telemetry.set_span_status(screenshot_span, "ok")
                except Exception as e:
                    self._telemetry.set_span_status(screenshot_span, "internal_error")
                    self._telemetry.set_span_data(screenshot_span, "error", str(e))
                    raise
                finally:
                    self._telemetry.finish_span(screenshot_span)

                # Call cloud /get_action endpoint
                inference_span = self._telemetry.start_span(
                    operation="http.client",
                    description="POST /get_action",
                    parent_span=step_transaction,
                )
                self._telemetry.set_span_tag(inference_span, "http.method", "POST")
                self._telemetry.set_span_data(inference_span, "http.url", f"{self._api_url}/get_action")

                request = GetActionRequest(
                    session_id=self._session_id,
                    image=screenshot_b64,
                    prompt=self._current_prompt or task,
                    phone_state="",
                    installed_packages="",
                    think=True,
                    agent_type=self._agent_type,
                    user_id=self._user_id,
                    platform=self._platform,
                    run_type=self._run_type,
                )

                inference_start_time = time.time()
                try:
                    response = await self._call_get_action(request)
                    self._telemetry.set_span_status(inference_span, "ok")
                    self._telemetry.set_span_data(inference_span, "http.status_code", 200)
                except Exception as e:
                    self._telemetry.set_span_status(inference_span, "internal_error")
                    self._telemetry.set_span_data(inference_span, "error", str(e))
                    raise
                finally:
                    latency_ms = (time.time() - inference_start_time) * 1000
                    self._telemetry.set_span_data(inference_span, "latency_ms", latency_ms)
                    self._telemetry.finish_span(inference_span)

                # Parse action string
                action = parse_action_string(response.action)
                action_type = action.get("type", "unknown")

                # Send real-time event for inference response
                self._telemetry.capture_message(
                    "[quantum.sdk] http_response",
                    level="info",
                    tags={
                        "event_name": "http_response",
                        "session_id": self._session_id,
                    },
                    extras={
                        "step": step,
                        "action_type": action_type,
                        "image_count": response.image_count,
                    },
                )

                # Check if confirmation is required
                if action_type == "confirm":
                    self._pending_confirmation = ConfirmationRequest(
                        action_description=action.get("message", "Confirm this action?"),
                        pending_action=action,
                        context={"step": step, "task": task},
                    )
                    if self._on_confirmation_required:
                        self._on_confirmation_required(self._pending_confirmation)
                    continue

                # Check if a question is being asked
                if action_type == "ask_question":
                    self._pending_question = QuestionRequest(
                        question=action.get("question", "Please provide input"),
                    )
                    if self._on_question_required:
                        self._on_question_required(self._pending_question)
                    continue

                # Check for task completion - enter paused state, don't return
                if action_type == "finish":
                    self._update_state(
                        status=AgentStatus.FINISH,
                        progress_message=action.get("summary") or action.get("message") or "Task completed successfully",
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
                            message=action.get("summary") or action.get("message") or "Task completed successfully",
                            steps_taken=step,
                            duration_seconds=time.time() - self._task_start_time,
                        )
                    # Otherwise, user added a message - continue the loop
                    self._update_state(status=AgentStatus.RUNNING)
                    continue

                # Check for failure
                if action_type == "fail":
                    self._update_state(
                        status=AgentStatus.FAIL,
                        error=action.get("reason", "Unknown error"),
                    )
                    step_status = "internal_error"
                    return TaskResult(
                        success=False,
                        message=action.get("reason", "Task failed"),
                        steps_taken=step,
                        duration_seconds=time.time() - self._task_start_time,
                    )

                # Execute the action with span tracking
                action_span = self._telemetry.start_span(
                    operation=f"action.{action_type}",
                    description=f"Execute {action_type}",
                    parent_span=step_transaction,
                )

                try:
                    await self._run_action(action)
                    self._telemetry.set_span_status(action_span, "ok")
                except Exception as e:
                    self._telemetry.set_span_status(action_span, "internal_error")
                    self._telemetry.set_span_data(action_span, "error", str(e))
                    raise
                finally:
                    self._telemetry.finish_span(action_span)

                await asyncio.sleep(self._step_delay)
            except Exception:
                step_status = "internal_error"
                raise
            finally:
                # Finish the step transaction
                self._telemetry.set_span_status(step_transaction, step_status)
                self._telemetry.finish_span(step_transaction)

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

    async def _call_get_action(self, request: GetActionRequest) -> GetActionResponse:
        """Call the /get_action endpoint"""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = await self._http_client.post(
            f"{self._api_url}/get_action",
            json=request.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        return GetActionResponse(**response.json())

    def send_message(self, message: str):
        """Send a user message to the agent.

        This can be used to provide additional context or instructions.
        If the agent is paused after a finish action, this will resume execution.
        """
        # Update the current prompt with the new message
        if self._current_prompt:
            self._current_prompt = f"{self._current_prompt}\n\nUser: {message}"
        else:
            self._current_prompt = message

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
