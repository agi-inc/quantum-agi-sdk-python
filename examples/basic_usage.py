"""
Basic usage example for the Quantum AGI SDK
"""

import asyncio
from quantum_agi_sdk import AGIClient, AgentState, AgentStatus


def on_status_change(state: AgentState):
    """Handle status changes from the agent"""
    status_emoji = {
        AgentStatus.IDLE: "⏸️",
        AgentStatus.RUNNING: "🏃",
        AgentStatus.PAUSE: "⏸️",
        AgentStatus.WAITING_CONFIRMATION: "❓",
        AgentStatus.FINISH: "✅",
        AgentStatus.FAIL: "❌",
    }
    emoji = status_emoji.get(state.status, "")
    print(f"{emoji} [{state.status.value}] Step {state.current_step}: {state.progress_message}")


def on_confirmation_required(confirmation):
    """Handle confirmation requests"""
    print(f"\n⚠️  CONFIRMATION REQUIRED ⚠️")
    print(f"Action: {confirmation.action_description}")
    print(f"Impact Level: {confirmation.impact_level}")

    # In a real application, you would show this in a UI
    # For this example, we auto-approve after user input
    response = input("Approve? (y/n): ").strip().lower()

    # Note: In async context, you'd use a different pattern
    # This is simplified for the example
    return response == 'y'


def on_action_executed(action: dict):
    """Handle executed actions"""
    action_type = action.get("type")
    if action_type == "click":
        print(f"  → Clicked at ({action.get('x')}, {action.get('y')})")
    elif action_type == "type":
        print(f"  → Typed: '{action.get('text')[:50]}...'")
    elif action_type == "key":
        print(f"  → Pressed: {action.get('key')}")
    elif action_type == "scroll":
        print(f"  → Scrolled {action.get('direction')}")


async def main():
    """Main example function"""
    print("=" * 50)
    print("Quantum AGI SDK - Basic Usage Example")
    print("=" * 50)

    # Create the client
    client = AGIClient(
        api_url="http://localhost:8000",  # Cloud inference server
        on_status_change=on_status_change,
        on_action_executed=on_action_executed,
        max_steps=50,
        step_delay=0.5,
    )

    # Example task - customize as needed
    task = "Open the default web browser and search for 'Lenovo ThinkPad X1 Carbon'"

    # Optional context from Quantum
    context = {
        "user_preferences": {
            "preferred_browser": "chrome",
            "search_engine": "google",
        },
        "user_memory": {
            "recently_searched": ["laptops", "monitors"],
        },
    }

    print(f"\nStarting task: {task}\n")

    try:
        # Execute the task
        result = await client.start(task=task, context=context)

        # Print result
        print("\n" + "=" * 50)
        print("TASK RESULT")
        print("=" * 50)
        print(f"Success: {result.success}")
        print(f"Message: {result.message}")
        print(f"Steps taken: {result.steps_taken}")
        print(f"Duration: {result.duration_seconds:.2f}s")

    except KeyboardInterrupt:
        print("\n\nTask interrupted by user")
        client.stop()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
