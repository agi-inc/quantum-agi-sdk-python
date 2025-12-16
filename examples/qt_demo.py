"""
Qt Demo Application for Quantum AGI SDK

A simple desktop application demonstrating the AGI SDK integration.
"""

import asyncio
import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QProgressBar,
    QMessageBox,
    QGroupBox,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from quantum_agi_sdk import AGIClient, AgentState, AgentStatus, ConfirmationRequest, TaskResult


class AgentWorker(QObject):
    """Worker thread for running the agent"""

    status_changed = pyqtSignal(AgentState)
    confirmation_required = pyqtSignal(ConfirmationRequest)
    action_executed = pyqtSignal(dict)
    task_completed = pyqtSignal(TaskResult)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_url: str):
        super().__init__()
        self._api_url = api_url
        self._client: Optional[AGIClient] = None
        self._task: Optional[str] = None
        self._context: Optional[dict] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_task(self, task: str, context: Optional[dict] = None):
        self._task = task
        self._context = context

    def run(self):
        """Run the agent task"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._client = AGIClient(
                api_url=self._api_url,
                on_status_change=lambda s: self.status_changed.emit(s),
                on_confirmation_required=lambda c: self.confirmation_required.emit(c),
                on_action_executed=lambda a: self.action_executed.emit(a),
            )

            result = self._loop.run_until_complete(
                self._client.start(self._task, self._context)
            )
            self.task_completed.emit(result)

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if self._client:
                self._loop.run_until_complete(self._client.close())
            self._loop.close()

    def pause(self):
        if self._client:
            self._client.pause()

    def resume(self):
        if self._client:
            self._client.resume()

    def end_session(self):
        if self._client:
            self._client.end_session()

    def confirm(self, confirmation_id: str, approved: bool):
        if self._client:
            self._client.confirm(confirmation_id, approved)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quantum AGI Demo")
        self.setMinimumSize(800, 600)

        self._worker: Optional[AgentWorker] = None
        self._thread: Optional[QThread] = None
        self._pending_confirmation: Optional[ConfirmationRequest] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("AGI Computer Use Agent")
        title.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Powered by Quantum Integration")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)

        # API URL input
        api_group = QGroupBox("Server Configuration")
        api_layout = QHBoxLayout(api_group)
        api_layout.addWidget(QLabel("API URL:"))
        self._api_url_input = QLineEdit("http://localhost:8000")
        api_layout.addWidget(self._api_url_input)
        layout.addWidget(api_group)

        # Task input
        task_group = QGroupBox("Task")
        task_layout = QVBoxLayout(task_group)
        task_layout.addWidget(QLabel("Enter your task:"))
        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText("e.g., Open Chrome and search for 'Lenovo laptops'")
        task_layout.addWidget(self._task_input)
        layout.addWidget(task_group)

        # Control buttons
        controls_layout = QHBoxLayout()

        self._start_btn = QPushButton("Start")
        self._start_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        self._start_btn.clicked.connect(self._on_start)
        controls_layout.addWidget(self._start_btn)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._on_pause)
        controls_layout.addWidget(self._pause_btn)

        self._resume_btn = QPushButton("Resume")
        self._resume_btn.setEnabled(False)
        self._resume_btn.clicked.connect(self._on_resume)
        controls_layout.addWidget(self._resume_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("background-color: #f44336; color: white; padding: 10px;")
        self._stop_btn.clicked.connect(self._on_stop)
        controls_layout.addWidget(self._stop_btn)

        layout.addLayout(controls_layout)

        # Progress
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self._status_label = QLabel("Status: Idle")
        self._status_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        progress_layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        self._step_label = QLabel("Step: 0")
        progress_layout.addWidget(self._step_label)

        layout.addWidget(progress_group)

        # Log output
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)
        self._log_output = QTextEdit()
        self._log_output.setReadOnly(True)
        self._log_output.setFont(QFont("Courier", 10))
        log_layout.addWidget(self._log_output)
        layout.addWidget(log_group)

    def _on_start(self):
        """Start the agent task"""
        task = self._task_input.text().strip()
        if not task:
            QMessageBox.warning(self, "Error", "Please enter a task")
            return

        api_url = self._api_url_input.text().strip()

        # Create worker and thread
        self._worker = AgentWorker(api_url)
        self._worker.set_task(task)

        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.confirmation_required.connect(self._on_confirmation_required)
        self._worker.action_executed.connect(self._on_action_executed)
        self._worker.task_completed.connect(self._on_task_completed)
        self._worker.error_occurred.connect(self._on_error)

        # Update UI
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)
        self._task_input.setEnabled(False)
        self._api_url_input.setEnabled(False)

        self._log("Starting task: " + task)

        # Start the thread
        self._thread.start()

    def _on_pause(self):
        """Pause the agent"""
        if self._worker:
            self._worker.pause()
            self._pause_btn.setEnabled(False)
            self._resume_btn.setEnabled(True)

    def _on_resume(self):
        """Resume the agent"""
        if self._worker:
            self._worker.resume()
            self._pause_btn.setEnabled(True)
            self._resume_btn.setEnabled(False)

    def _on_stop(self):
        """End the agent session"""
        if self._worker:
            self._worker.end_session()
        self._cleanup_thread()

    def _on_status_changed(self, state: AgentState):
        """Handle status changes"""
        status_colors = {
            AgentStatus.IDLE: "#666",
            AgentStatus.RUNNING: "#4CAF50",
            AgentStatus.PAUSED: "#FF9800",
            AgentStatus.WAITING_CONFIRMATION: "#2196F3",
            AgentStatus.COMPLETED: "#4CAF50",
            AgentStatus.FAILED: "#f44336",
            AgentStatus.STOPPED: "#9E9E9E",
        }

        color = status_colors.get(state.status, "#666")
        self._status_label.setText(f"Status: {state.status.value}")
        self._status_label.setStyleSheet(f"color: {color};")

        self._step_label.setText(f"Step: {state.current_step}")

        if state.progress_message:
            self._log(f"[{state.status.value}] {state.progress_message}")

        # Update progress bar (approximate)
        if state.current_step > 0:
            progress = min(state.current_step * 10, 100)
            self._progress_bar.setValue(progress)

    def _on_confirmation_required(self, confirmation: ConfirmationRequest):
        """Handle confirmation request"""
        self._pending_confirmation = confirmation

        result = QMessageBox.question(
            self,
            "Confirmation Required",
            f"The agent wants to perform a high-impact action:\n\n"
            f"{confirmation.action_description}\n\n"
            f"Impact Level: {confirmation.impact_level}\n\n"
            f"Do you want to approve this action?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        approved = result == QMessageBox.StandardButton.Yes
        if self._worker:
            self._worker.confirm(confirmation.id, approved)

        self._log(f"Confirmation {'approved' if approved else 'denied'}: {confirmation.action_description}")

    def _on_action_executed(self, action: dict):
        """Handle executed action"""
        action_type = action.get("type")
        if action_type == "click":
            self._log(f"  → Click at ({action.get('x')}, {action.get('y')})")
        elif action_type == "type":
            text = action.get("text", "")[:30]
            self._log(f"  → Type: '{text}'...")
        elif action_type == "key":
            self._log(f"  → Key: {action.get('key')}")
        elif action_type == "scroll":
            self._log(f"  → Scroll {action.get('direction')}")
        else:
            self._log(f"  → Action: {action_type}")

    def _on_task_completed(self, result: TaskResult):
        """Handle task completion"""
        self._progress_bar.setValue(100 if result.success else 0)

        if result.success:
            self._log(f"\n✓ Task completed successfully!")
            self._log(f"  Steps: {result.steps_taken}")
            self._log(f"  Duration: {result.duration_seconds:.2f}s")
            QMessageBox.information(self, "Success", result.message)
        else:
            self._log(f"\n✗ Task failed: {result.message}")
            QMessageBox.warning(self, "Failed", result.message)

        self._cleanup_thread()

    def _on_error(self, error: str):
        """Handle error"""
        self._log(f"\n✗ Error: {error}")
        QMessageBox.critical(self, "Error", error)
        self._cleanup_thread()

    def _cleanup_thread(self):
        """Clean up the worker thread"""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None

        # Reset UI
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._resume_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._task_input.setEnabled(True)
        self._api_url_input.setEnabled(True)

    def _log(self, message: str):
        """Add message to log"""
        self._log_output.append(message)
        # Auto-scroll to bottom
        scrollbar = self._log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        """Handle window close"""
        if self._worker:
            self._worker.end_session()
        self._cleanup_thread()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
