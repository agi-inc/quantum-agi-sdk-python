# Quantum AGI SDK (Python)

Computer Use Agent SDK for Quantum Integration - Python Implementation

## Overview

This SDK enables Quantum to orchestrate an AI agent that can control a PC to complete tasks on behalf of users. The agent uses vision-based UI understanding to navigate applications, browsers, and OS settings.

## Architecture

```
Quantum (intent + context + memory)
         ↓ start(task)
AGI SDK (local device agent)
         ↓ enters task loop
Agent Step (screenshot → cloud inference → action JSON)
         ↓
AGI SDK (executes action locally)
         ↓
Repeat until task completion or confirmation needed
```

## Installation

```bash
pip install quantum-agi-sdk
```

Or install from source:

```bash
git clone https://github.com/agi-inc/quantum-agi-sdk-python
cd quantum-agi-sdk-python
pip install -e .
```

## Quick Start

```python
import asyncio
from quantum_agi_sdk import AGIClient, AgentState

def on_status_change(state: AgentState):
    print(f"Status: {state.status} - {state.progress_message}")

def on_confirmation(confirmation):
    print(f"Confirmation needed: {confirmation.action_description}")
    # In a real app, show UI and get user input
    client.confirm(confirmation.id, approved=True)

async def main():
    client = AGIClient(
        api_url="https://api.agi.tech",
        on_status_change=on_status_change,
        on_confirmation_required=on_confirmation,
    )

    result = await client.start(
        task="Open Chrome and search for 'Lenovo laptops'",
        context={"user_preference": "prefer_chrome"}
    )

    print(f"Task completed: {result.success}")
    print(f"Steps taken: {result.steps_taken}")

    await client.close()

asyncio.run(main())
```

## API Reference

### Core Components

- **AGIClient**: Main orchestration client
- **ScreenCapture**: Screenshot capture with 1000x1000 scaling
- **ActionExecutor**: Local action execution (click, type, scroll, etc.)
- **Models**: Pydantic models for actions, states, and API contracts

### AGIClient

The main interface for the SDK.

#### Constructor

```python
AGIClient(
    api_url: str = "https://api.agi.tech",
    api_key: Optional[str] = None,
    on_status_change: Optional[Callable[[AgentState], None]] = None,
    on_confirmation_required: Optional[Callable[[ConfirmationRequest], None]] = None,
    on_action_executed: Optional[Callable[[dict], None]] = None,
    max_steps: int = 100,
    step_delay: float = 0.5,
)
```

**Parameters:**
- `api_url`: URL of the AGI cloud inference API (default: "https://api.agi.tech")
- `api_key`: Optional API key for authentication
- `on_status_change`: Callback function called when agent status changes
- `on_confirmation_required`: Callback function called when user confirmation is needed
- `on_action_executed`: Callback function called after each action is executed
- `max_steps`: Maximum number of steps before stopping (default: 100)
- `step_delay`: Delay between steps in seconds (default: 0.5)

#### Methods

- `start(task: str, context: Optional[dict] = None) -> TaskResult`: Start executing a task
- `pause()`: Pause agent execution
- `resume()`: Resume paused execution
- `stop()`: Stop agent completely
- `confirm(confirmation_id: str, approved: bool = True)`: Respond to confirmation request
- `interrupt(message: str)`: Interrupt the agent with a user message
- `close()`: Close the HTTP client and cleanup resources

### Action Types

The agent can perform these actions:

| Action | Description | Parameters |
|--------|-------------|------------|
| `click` | Click at coordinates | `x`, `y`, `button` |
| `double_click` | Double-click at coordinates | `x`, `y` |
| `right_click` | Right-click at coordinates | `x`, `y` |
| `type` | Type text | `text` |
| `key` | Press key or combination | `key` (e.g., 'enter', 'ctrl+c', 'cmd+v') |
| `scroll` | Scroll in a direction | `x`, `y`, `direction`, `amount` |
| `drag` | Drag from point to point | `start_x`, `start_y`, `end_x`, `end_y` |
| `wait` | Wait for duration | `duration` (seconds) |
| `screenshot` | Take a screenshot | - |
| `finish` | Task completed | `message` |
| `fail` | Task failed | `reason` |
| `confirm` | Request user confirmation | `action_description`, `impact_level`, `pending_action` |

### Agent States

The agent can be in one of these states:

- `IDLE`: Agent is idle and ready
- `RUNNING`: Agent is actively executing steps
- `PAUSE`: Agent is paused
- `WAITING_CONFIRMATION`: Agent is waiting for user confirmation
- `FINISH`: Task completed successfully
- `FAIL`: Task failed

### Data Models

#### AgentState
```python
class AgentState:
    status: AgentStatus
    task: Optional[str]
    current_step: int
    total_steps: Optional[int]
    last_action: Optional[Action]
    progress_message: Optional[str]
    error: Optional[str]
```

#### TaskResult
```python
class TaskResult:
    success: bool
    message: str
    steps_taken: int
    duration_seconds: float
    final_state: Optional[dict]
```

#### ConfirmationRequest
```python
class ConfirmationRequest:
    id: str
    action_description: str
    impact_level: str  # "low", "medium", "high"
    pending_action: dict
    context: Optional[dict]
```

## Configuration

### Environment Variables

You can configure the SDK using environment variables:

```bash
# API endpoint
export QUANTUM_AGI_API_URL="https://api.agi.tech"

# API key (if required)
export QUANTUM_AGI_API_KEY="your-api-key"
```

### Context Object

The context object allows you to pass additional information to the agent:

```python
context = {
    "user_preferences": {
        "preferred_browser": "chrome",
        "search_engine": "google",
    },
    "user_memory": {
        "recently_searched": ["laptops", "monitors"],
    },
    "device_info": {
        "os": "macos",
        "screen_resolution": "2560x1440",
    },
}

result = await client.start(task="Search for laptops", context=context)
```

## Cloud Server

The SDK requires a cloud inference server running. See the [quantum-agi-cloud](https://github.com/agi-inc/quantum-agi-cloud) repository for the server implementation.

```bash
# Install and run the cloud server
pip install quantum-agi-cloud
quantum-agi-server
```

Or use the AGI API service at https://api.agi.inc

## Safety Features

- **Confirmation Flow**: High-impact actions (purchases, bookings, deletions) require user confirmation
- **Failsafe**: Move mouse to screen corner to abort (pyautogui failsafe)
- **Step Limit**: Default maximum of 100 steps per task
- **Pause/Stop**: Agent can be paused or stopped at any time
- **Interrupt**: Send messages to the agent during execution to provide guidance

## Examples

### Basic Usage

See [examples/basic_usage.py](examples/basic_usage.py) for a simple command-line example.

```bash
python examples/basic_usage.py
```

### Qt Desktop Application

See [examples/qt_demo.py](examples/qt_demo.py) for a full PyQt6 desktop application example.

```bash
pip install PyQt6
python examples/qt_demo.py
```

### Custom Callbacks

```python
def on_status_change(state: AgentState):
    if state.status == AgentStatus.RUNNING:
        print(f"Step {state.current_step}: {state.progress_message}")
    elif state.status == AgentStatus.FAIL:
        print(f"Error: {state.error}")

def on_action_executed(action: dict):
    action_type = action.get("type")
    if action_type == "click":
        print(f"Clicked at ({action['x']}, {action['y']})")
    elif action_type == "type":
        print(f"Typed: {action['text']}")

client = AGIClient(
    api_url="https://api.agi.tech",
    on_status_change=on_status_change,
    on_action_executed=on_action_executed,
)
```

## Demo Applications

See the demo repositories:
- [quantum-agi-qt-demo](https://github.com/agi-inc/quantum-agi-qt-demo) - PyQt6 desktop application
- [quantum-agi-electron-demo](https://github.com/agi-inc/quantum-agi-electron-demo) - Electron desktop application

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/agi-inc/quantum-agi-sdk-python
cd quantum-agi-sdk-python

# Install dev dependencies
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
# Format code
black quantum_agi_sdk

# Check linting
ruff check quantum_agi_sdk
```

### Build Package

```bash
pip install build
python -m build
```

## Troubleshooting

### "Connection refused" error

Make sure the cloud inference server is running:
```bash
quantum-agi-server
```

### Permission errors on macOS

Grant accessibility permissions to your terminal or Python application:
1. System Settings → Privacy & Security → Accessibility
2. Add your terminal app or Python executable

### Screenshots not capturing correctly

Ensure the screen resolution matches expected dimensions (default 1000x1000 scaling).

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Support

For questions or issues:
- GitHub Issues: https://github.com/agi-inc/quantum-agi-sdk-python/issues
- Email: dev@agi.inc
