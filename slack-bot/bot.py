#!/usr/bin/env python3
"""
Kiro Remote Approve - Slack Bot (Socket Mode with slack_bolt)

Sends a DM asking for approval, then listens for the response via Socket Mode.
No public URL needed — works from anywhere including your phone.

Install dependencies:
  pip install slack_bolt

Environment variables:
  SLACK_BOT_TOKEN  - Bot User OAuth Token (xoxb-...)
  SLACK_APP_TOKEN  - App-Level Token (xapp-...) with connections:write scope
  SLACK_USER_ID    - Slack User ID to send the approval DM to
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# === Load .env if present ===
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from core.config import SELECTORS
from core.cdp import (
    do_click, get_ws_url, check_pending_approval,
    send_message_to_agent, get_agent_output, is_agent_busy,
)

# === Configuration ===
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_USER_ID = os.environ.get("SLACK_USER_ID", "")

if not SLACK_BOT_TOKEN:
    print("ERROR: Set SLACK_BOT_TOKEN (xoxb-...)")
    sys.exit(1)
if not SLACK_APP_TOKEN:
    print("ERROR: Set SLACK_APP_TOKEN (xapp-...)")
    sys.exit(1)
if not SLACK_USER_ID:
    print("ERROR: Set SLACK_USER_ID (the user to DM for approval)")
    sys.exit(1)

# === Initialize the Bolt App ===
app = App(token=SLACK_BOT_TOKEN)


# === CDP actions for button handlers ===
def execute_approve():
    """Click the approve button in Kiro via CDP."""
    result = do_click("approve")
    print(f"[Agent] Approve: {result}")
    return result


def execute_reject():
    """Click the reject button in Kiro via CDP."""
    result = do_click("reject")
    print(f"[Agent] Reject: {result}")
    return result


def execute_trust():
    """Click the trust button in Kiro via CDP."""
    result = do_click("trust")
    print(f"[Agent] Trust: {result}")
    return result


# === Placeholder kept for compatibility ===
def execute_local_agent_task():
    """Alias for approve action."""
    return execute_approve()


# === Step 1: Send the approval DM ===
def send_approval_request(command_text="(pending command)"):
    """Open a DM with the user and send an approval request with buttons."""
    # Open a DM conversation with the target user
    result = app.client.conversations_open(users=[SLACK_USER_ID])
    if not result.get("ok"):
        print(f"ERROR: Could not open DM — {result.get('error')}")
        sys.exit(1)

    channel_id = result["channel"]["id"]

    # Send the approval message with interactive buttons
    app.client.chat_postMessage(
        channel=channel_id,
        text=f"🔔 Kiro needs approval: {command_text}",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔔 *Kiro needs approval*",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{command_text}```",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Run"},
                        "style": "primary",
                        "action_id": "approve",
                        "value": "approve",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "action_id": "reject",
                        "value": "reject",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔄 Trust"},
                        "action_id": "trust",
                        "value": "trust",
                    },
                ],
            },
        ],
    )
    print(f"[Slack] Approval request sent to user {SLACK_USER_ID}")
    return channel_id


# === Step 2 & 3: Listen for button clicks ===
@app.action("approve")
def handle_approve(ack, body):
    """Handle the ✅ Run button click."""
    ack()
    result = execute_approve()
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]
    original_blocks = body["message"].get("blocks", [])
    # Keep content blocks, remove actions, add result
    updated_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    updated_blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"✅ *Approved* — {result}"},
    })
    app.client.chat_update(
        channel=channel,
        ts=ts,
        text=f"✅ Approved — {result}",
        blocks=updated_blocks,
    )


@app.action("reject")
def handle_reject(ack, body):
    """Handle the ❌ Reject button click."""
    ack()
    result = execute_reject()
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]
    original_blocks = body["message"].get("blocks", [])
    updated_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    updated_blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"❌ *Rejected* — {result}"},
    })
    app.client.chat_update(
        channel=channel,
        ts=ts,
        text=f"❌ Rejected — {result}",
        blocks=updated_blocks,
    )


@app.action("trust")
def handle_trust(ack, body):
    """Handle the 🔄 Trust button click."""
    ack()
    result = execute_trust()
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]
    original_blocks = body["message"].get("blocks", [])
    updated_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    updated_blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"🔄 *Trusted* — {result}"},
    })
    app.client.chat_update(
        channel=channel,
        ts=ts,
        text=f"🔄 Trusted — {result}",
        blocks=updated_blocks,
    )


# === State for agent completion watcher ===
waiting_for_agent = False
agent_was_busy = False
dm_channel_id = None  # Will be set in main()


# === Also handle text replies in DM ===
@app.event("message")
def handle_message(event, say):
    """
    Handle incoming DM text messages.
    Reacts to y/n/t (case-insensitive).
    Any other text is sent directly to the agent chat.
    """
    global waiting_for_agent, agent_was_busy

    # Only process messages from the target user
    user = event.get("user", "")
    if user != SLACK_USER_ID:
        return

    # Ignore bot messages, edits, and subtypes
    if event.get("bot_id") or event.get("subtype"):
        return

    text = event.get("text", "").strip()
    text_lower = text.lower()

    if text_lower in ("y", "yes", "ok", "go", "run"):
        result = execute_approve()
        say(f"✅ {result}")

    elif text_lower in ("n", "no", "nope", "stop"):
        result = execute_reject()
        say(f"❌ {result}")

    elif text_lower in ("t", "trust", "always"):
        result = execute_trust()
        say(f"🔄 {result}")

    elif text_lower in ("status", "ping"):
        ws = get_ws_url()
        if ws:
            busy = is_agent_busy()
            status = "🟡 Agent is working..." if busy else "🟢 Agent idle"
            say(f"🟢 Kiro is connected\n{status}")
        else:
            say("🔴 Cannot reach Kiro — make sure it's running with `--remote-debugging-port=9229`")

    elif text_lower == "output":
        output = get_agent_output(max_lines=15)
        if output:
            # Truncate if too long for Slack message
            if len(output) > 2800:
                output = output[-2800:]
            say(f"🤖 *Last agent output:*\n```{output}```")
        else:
            say("⚠️ No agent output found")

    elif text_lower in ("help", "?"):
        say(
            "🤖 *Kiro Remote Approve*\n\n"
            "Commands:\n"
            "• `y` / `yes` → Run (approve)\n"
            "• `n` / `no` → Reject\n"
            "• `t` / `trust` → Trust (always approve)\n"
            "• `output` → Get last agent output\n"
            "• `status` → Check Kiro connection\n"
            "• `help` → Show this message\n\n"
            "Any other text → sent directly to agent chat"
        )

    else:
        # Send any other text directly to the agent
        result = send_message_to_agent(text)
        say(f"📨 {result}")
        if "Sent" in result:
            waiting_for_agent = True
            agent_was_busy = False


# === Agent Completion Watcher ===
def poll_agent_completion():
    """Watch for agent to finish after we sent a message."""
    global waiting_for_agent, agent_was_busy, dm_channel_id

    if not waiting_for_agent:
        return

    busy = is_agent_busy()

    if busy:
        agent_was_busy = True
    elif agent_was_busy and not busy:
        # Agent was busy and now stopped — it finished
        waiting_for_agent = False
        agent_was_busy = False
        # Give it a moment for final render
        import time
        time.sleep(1)
        output = get_agent_output(max_lines=15)
        if output:
            if len(output) > 2800:
                output = output[-2800:]
            app.client.chat_postMessage(
                channel=dm_channel_id,
                text=f"✅ *Agent finished:*\n```{output}```",
            )
        else:
            app.client.chat_postMessage(
                channel=dm_channel_id,
                text="✅ Agent finished (no output captured)",
            )


# === Main ===
def main():
    global dm_channel_id

    print("[Slack] Starting Socket Mode bot...")

    # Open DM channel for later use
    result = app.client.conversations_open(users=[SLACK_USER_ID])
    if not result.get("ok"):
        print(f"ERROR: Could not open DM — {result.get('error')}")
        sys.exit(1)

    dm_channel_id = result["channel"]["id"]

    # Send a simple welcome message
    app.client.chat_postMessage(
        channel=dm_channel_id,
        text="🟢 Kiro Remote Approve bot started — send `help` for commands.",
    )

    # Start Socket Mode handler in a background thread
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.connect()
    print("[Slack] Listening via Socket Mode...")

    # Poll Kiro for pending approvals in the main thread
    import time
    last_notified_command = None

    while True:
        try:
            pending = check_pending_approval()
            if pending and pending != "null" and pending != last_notified_command:
                last_notified_command = pending
                cmd_text = pending if pending != "PENDING_NO_CMD" else "(unknown command)"
                send_approval_request(cmd_text)
            elif not pending:
                last_notified_command = None
            poll_agent_completion()
            time.sleep(3)
        except KeyboardInterrupt:
            print("[Slack] Shutting down.")
            handler.close()
            break
        except Exception as e:
            print(f"[Slack] Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
