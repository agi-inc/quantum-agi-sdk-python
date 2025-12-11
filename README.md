# Quantum AGI SDK (Python)

Computer Use Agent SDK for Quantum Integration - Python Implementation

## Overview

This SDK enables Quantum to orchestrate an AI agent that can control a PC to complete tasks on behalf of users. The agent uses vision-based UI understanding to navigate applications, browsers, and OS settings.

## Architecture

```
Quantum (intent + context + memory)
         ↓ start(task)
CUA SDK (local device agent)
         ↓ enters task loop
Agent Step (screenshot → cloud inference → action JSON)
         ↓
CUA SDK (executes action locally)
         ↓
Repeat until task completion or confirmation needed
```

## Installation

```bash
pip install quantum-agi-sdk
```

For server components:
```bash
pip install quantum-agi-sdk[server]
```

## Quick Start

```python
import asyncio
from quantum_agi_sdk import CUAClient, AgentState

def on_status_change(state: AgentState):
    print(f"Status: {state.status} - {state.progress_message}")

def on_confirmation(confirmation):
    print(f"Confirmation needed: {confirmation.action_description}")
    # In a real app, show UI and get user input
    client.confirm(confirmation.id, approved=True)

async def main():
    client = CUAClient(
        api_url="http://localhost:8000",
        on_status_change=on_status_change,
        on_confirmation_required=on_confirmation,
    )

    result = await client.start(
        task="Open Chrome and search for 'Lenovo laptops'",
        context={"user_preference": "prefer_chrome"}
    )

    print(f"Task completed: {result.success}")
    print(f"Steps taken: {result.steps_taken}")

asyncio.run(main())
```

## API Reference

### CUAClient

The main interface for the SDK.

#### Constructor

```python
CUAClient(
    api_url: str = "http://localhost:8000",
    api_key: Optional[str] = None,
    on_status_change: Optional[Callable[[AgentState], None]] = None,
    on_confirmation_required: Optional[Callable[[ConfirmationRequest], None]] = None,
    on_action_executed: Optional[Callable[[dict], None]] = None,
    max_steps: int = 100,
    step_delay: float = 0.5,
)
```

#### Methods

- `start(task: str, context: Optional[dict] = None) -> TaskResult`: Start executing a task
- `pause()`: Pause agent execution
- `resume()`: Resume paused execution
- `stop()`: Stop agent completely
- `confirm(confirmation_id: str, approved: bool = True)`: Respond to confirmation request

### Action Types

The agent can perform these actions:

| Action | Description |
|--------|-------------|
| `click` | Click at coordinates |
| `double_click` | Double-click at coordinates |
| `right_click` | Right-click at coordinates |
| `type` | Type text |
| `key` | Press key or combination |
| `scroll` | Scroll in a direction |
| `drag` | Drag from point to point |
| `wait` | Wait for duration |
| `done` | Task completed |
| `fail` | Task failed |
| `confirm` | Request user confirmation |

## Running the Cloud Server

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here

# Run the server
python -m quantum_agi_sdk.cloud.server
```

Or programmatically:

```python
from quantum_agi_sdk.cloud import create_app
import uvicorn

app = create_app()
uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Safety Features

- **Confirmation Flow**: High-impact actions (purchases, bookings, deletions) require user confirmation
- **Failsafe**: Move mouse to screen corner to abort (pyautogui failsafe)
- **Step Limit**: Default maximum of 100 steps per task
- **Pause/Stop**: Agent can be paused or stopped at any time

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,server]"

# Run tests
pytest

# Format code
black quantum_agi_sdk
ruff check quantum_agi_sdk
```

## License

MIT
