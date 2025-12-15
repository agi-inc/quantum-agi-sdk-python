"""
Main AGI Client - The primary SDK interface
"""

import asyncio
import time
import uuid
from typing import Callable, Optional

import httpx

from quantum_agi_sdk.capture import ScreenCapture
from quantum_agi_sdk.executor import ActionExecutor
from quantum_agi_sdk.models import (
    AgentState,
    AgentStatus,
    ConfirmationRequest,
    TaskResult,
    StartSessionRequest,
    StartSessionResponse,
    QuantumInferenceRequest,
    QuantumInferenceResponse,
    FinishSessionRequest,
    FinishSessionResponse,
    InterruptRequest,
    InterruptResponse,
)


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
        api_url: str = "https://api.agi.tech",
        api_key: Optional[str] = None,
        on_status_change: Optional[Callable[[AgentState], None]] = None,
        on_confirmation_required: Optional[Callable[[ConfirmationRequest], None]] = None,
        on_action_executed: Optional[Callable[[dict], None]] = None,
        max_steps: int = 100,
        step_delay: float = 0.5,
    ):
        """
        Initialize the AGI Client.

        Args:
            api_url: URL of the AGI cloud inference API
            api_key: API key for authentication
            on_status_change: Callback for agent status changes
            on_confirmation_required: Callback when user confirmation is needed
            on_action_executed: Callback after each action is executed
            max_steps: Maximum steps before stopping
            step_delay: Delay between steps in seconds
        """
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._on_status_change = on_status_change
        self._on_confirmation_required = on_confirmation_required
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
        self._action_history: list[dict] = []
        self._task_start_time: Optional[float] = None
        self._session_id: Optional[str] = None

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
        self._action_history = []
        self._task_start_time = time.time()

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

                if not self._confirmed:
                    self._pending_confirmation = None
                    self._update_state(
                        status=AgentStatus.FINISH,
                        progress_message="User denied confirmation",
                    )
                    return TaskResult(
                        success=False,
                        message="User denied confirmation",
                        steps_taken=step,
                        duration_seconds=time.time() - self._task_start_time,
                    )

                if self._pending_confirmation.pending_action:
                    await self._run_action(self._pending_confirmation.pending_action)
                self._pending_confirmation = None
                self._update_state(status=AgentStatus.RUNNING)
                continue

            step += 1
            self._update_state(
                current_step=step,
                progress_message=f"Executing step {step}...",
            )

            # Capture screenshot
            screenshot_b64 = self._capture.capture()

            # Get next action from cloud inference
            request = QuantumInferenceRequest(
                screenshot_base64=screenshot_b64,
                history=self._action_history[-10:],
            )

            response = await self._call_quantum_inference(request)
            action = response.action

            # Check if confirmation is required
            if response.requires_confirmation or action.get("type") == "confirm":
                self._pending_confirmation = ConfirmationRequest(
                    id=str(uuid.uuid4()),
                    action_description=action.get(
                        "action_description", response.reasoning or "Confirm this action?"
                    ),
                    impact_level=action.get("impact_level", "high"),
                    pending_action=action.get("pending_action", action),
                    context={"step": step, "task": task},
                )
                if self._on_confirmation_required:
                    self._on_confirmation_required(self._pending_confirmation)
                continue

            # Check for task completion
            if action.get("type") == "done":
                self._update_state(
                    status=AgentStatus.FINISH,
                    progress_message=action.get("message", "Task completed successfully"),
                )
                return TaskResult(
                    success=True,
                    message=action.get("message", "Task completed successfully"),
                    steps_taken=step,
                    duration_seconds=time.time() - self._task_start_time,
                )

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
            self._action_history.append(action)
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

    async def interrupt(self, message: str) -> InterruptResponse:
        """Send an interruption message to the agent."""
        if not self._session_id:
            raise RuntimeError("No active session")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = InterruptRequest(message=message)
        response = await self._http_client.post(
            f"{self._api_url}/v1/quantum/sessions/{self._session_id}/interrupt",
            json=request.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        return InterruptResponse(**response.json())

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

    def stop(self):
        """Stop the agent execution completely."""
        self._running = False
        self._paused = False
        self._update_state(status=AgentStatus.FINISH, progress_message="Agent stopped by user")
        self._confirmed = False
        self._confirmation_event.set()

    def confirm(self, confirmation_id: str, approved: bool = True):
        """Respond to a confirmation request."""
        if not self._pending_confirmation:
            return
        if self._pending_confirmation.id != confirmation_id:
            return
        self._confirmed = approved
        self._confirmation_event.set()

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

    def stop(self):
        self._async_client.stop()

    def confirm(self, confirmation_id: str, approved: bool = True):
        self._async_client.confirm(confirmation_id, approved)

    def interrupt(self, message: str) -> InterruptResponse:
        return self._loop.run_until_complete(self._async_client.interrupt(message))

    @property
    def state(self) -> AgentState:
        return self._async_client.state

    def close(self):
        self._loop.run_until_complete(self._async_client.close())
        self._loop.close()
