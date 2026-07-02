import time
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path("agent_logs.jsonl")


def log_event(event: dict):
    """Append one event to the log file as a JSON line."""
    event["id"] = str(uuid.uuid4())
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")
    print(f"[SENTRY] Logged: {event['type']} — {event.get('model', '')} "
          f"({event.get('duration_ms', '?')}ms)")


def monitor_call(func):
    """
    Decorator — wrap any function that calls an AI API and log what happens.

    Usage:
        @monitor_call
        def ask_agent(prompt):
            return openai_client.chat.completions.create(...)
    """
    def wrapper(*args, **kwargs):
        start = time.time()
        error = None
        result = None

        try:
            result = func(*args, **kwargs)
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration_ms = round((time.time() - start) * 1000)

            # Pull out what we can from args/kwargs for logging
            messages = kwargs.get("messages") or (args[0] if args else None)
            model = kwargs.get("model", "unknown")

            log_event({
                "type": "ai_call",
                "function": func.__name__,
                "model": model,
                "duration_ms": duration_ms,
                "input_preview": str(messages)[:200] if messages else None,
                "error": error,
                "success": error is None,
            })

        return result
    return wrapper


# --- Demo: simulate an AI call without needing an API key ---
if __name__ == "__main__":
    print("=== Sentry Logger — First Test ===\n")

    @monitor_call
    def fake_agent_call(messages, model="gpt-4o"):
        time.sleep(0.3)  # simulate network latency
        return {"role": "assistant", "content": "Order confirmed for customer #4821."}

    # Simulate 3 agent actions
    fake_agent_call(
        messages=[{"role": "user", "content": "Process refund for order #4821"}],
        model="gpt-4o"
    )
    fake_agent_call(
        messages=[{"role": "user", "content": "Email customer confirmation"}],
        model="gpt-4o"
    )
    fake_agent_call(
        messages=[{"role": "user", "content": "Update CRM record"}],
        model="gpt-4o-mini"
    )

    print(f"\nLog file: {LOG_FILE.resolve()}")
    print("\nRaw log contents:")
    for line in LOG_FILE.read_text().strip().split("\n"):
        entry = json.loads(line)
        print(f"  {entry['timestamp']}  {entry['type']}  {entry['model']}  {entry['duration_ms']}ms  success={entry['success']}")
