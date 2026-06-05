#!/usr/bin/env python3
"""
Kiro Remote Approve - Telegram Bot

Approve/reject Kiro agent commands from your phone via Telegram.
Uses shared CDP core for button clicking.

Usage:
  python3 telegram-bot/bot.py

Environment variables:
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Your chat ID from @userinfobot
  CDP_PORT            - Kiro debug port (default: 9229)
"""

import os
import sys
import json
import time
import signal
import urllib.request
import urllib.error

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_env, SELECTORS
from core.cdp import (
    do_click, get_ws_url, check_pending_approval,
    send_message_to_agent, get_agent_output, is_agent_busy,
)

# Load environment
load_env()

# === Configuration ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# === State ===
last_update_id = 0
running = True
last_notified_command = None
waiting_for_agent = False  # True when we sent a message and await response
agent_was_busy = False     # Track agent busy state for finish detection


# === Telegram API ===
def telegram_api(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(text, reply_markup=None):
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return telegram_api("sendMessage", data)


# === Message Handlers ===
def handle_callback(callback_query):
    data = callback_query.get("data", "")
    callback_id = callback_query.get("id", "")
    from_user = str(callback_query.get("from", {}).get("id", ""))

    if from_user != str(CHAT_ID):
        telegram_api("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": "⛔ Unauthorized",
            "show_alert": True,
        })
        return

    if data in SELECTORS:
        result = do_click(data)
        telegram_api("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": result,
        })
        message = callback_query.get("message", {})
        if message.get("message_id"):
            telegram_api("editMessageText", {
                "chat_id": CHAT_ID,
                "message_id": message["message_id"],
                "text": f"{message.get('text', '')}\n\n→ {result}",
                "parse_mode": "HTML",
            })


def handle_message(message):
    global waiting_for_agent, agent_was_busy

    text = message.get("text", "").strip()
    text_lower = text.lower()
    from_user = str(message.get("from", {}).get("id", ""))

    if from_user != str(CHAT_ID):
        return

    if text_lower in ("/start", "/help"):
        send_message(
            "🤖 <b>Kiro Remote Approve</b>\n\n"
            "Commands:\n"
            "  <b>y</b> / <b>yes</b> → Run (approve)\n"
            "  <b>n</b> / <b>no</b> → Reject\n"
            "  <b>t</b> / <b>trust</b> → Trust (always approve)\n"
            "  /buttons → Show buttons\n"
            "  /status → Check Kiro connection\n"
            "  /output → Get last agent output\n\n"
            "Any other text → sent directly to agent chat"
        )
    elif text_lower in ("y", "yes", "ok", "go", "/approve", "run"):
        result = do_click("approve")
        send_message(result)
    elif text_lower in ("n", "no", "nope", "stop", "/reject"):
        result = do_click("reject")
        send_message(result)
    elif text_lower in ("t", "trust", "always", "/trust"):
        result = do_click("trust")
        send_message(result)
    elif text_lower == "/buttons":
        send_message("🤖 <b>Approve?</b>", reply_markup={
            "inline_keyboard": [[
                {"text": "✅ Run", "callback_data": "approve"},
                {"text": "❌ Reject", "callback_data": "reject"},
                {"text": "🔄 Trust", "callback_data": "trust"},
            ]]
        })
    elif text_lower == "/status":
        ws = get_ws_url()
        if ws:
            busy = is_agent_busy()
            status = "🟡 Agent is working..." if busy else "🟢 Agent idle"
            send_message(f"🟢 <b>Kiro is connected</b>\n{status}")
        else:
            send_message(
                "🔴 <b>Cannot reach Kiro</b>\n\n"
                "Make sure it's running with "
                "--remote-debugging-port=9229"
            )
    elif text_lower == "/output":
        output = get_agent_output(max_lines=15)
        if output:
            # Truncate if too long for Telegram (4096 char limit)
            if len(output) > 3500:
                output = output[-3500:]
            send_message(f"🤖 <b>Last agent output:</b>\n\n<pre>{output}</pre>")
        else:
            send_message("⚠️ No agent output found")
    else:
        # Send any other text directly to the agent
        result = send_message_to_agent(text)
        send_message(result)
        if "Sent" in result:
            waiting_for_agent = True
            agent_was_busy = False


# === Agent Completion Watcher ===
def poll_agent_completion():
    """Watch for agent to finish after we sent a message."""
    global waiting_for_agent, agent_was_busy

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
        time.sleep(1)
        output = get_agent_output(max_lines=15)
        if output:
            if len(output) > 3500:
                output = output[-3500:]
            send_message(
                f"✅ <b>Agent finished:</b>\n\n<pre>{output}</pre>"
            )
        else:
            send_message("✅ Agent finished (no output captured)")


# === Approval Watcher ===
def poll_for_approvals():
    """Check for pending approvals and notify."""
    global last_notified_command

    result = check_pending_approval()
    if result and result != "null" and result != last_notified_command:
        last_notified_command = result
        cmd_text = result if result != "PENDING_NO_CMD" else "(unknown command)"
        send_message(
            f"🔔 <b>Kiro needs approval</b>\n\n<code>{cmd_text}</code>",
            reply_markup={
                "inline_keyboard": [[
                    {"text": "✅ Run", "callback_data": "approve"},
                    {"text": "❌ Reject", "callback_data": "reject"},
                    {"text": "🔄 Trust", "callback_data": "trust"},
                ]]
            }
        )
    elif not result:
        last_notified_command = None


# === Main Loop ===
def poll_updates():
    global last_update_id
    result = telegram_api("getUpdates", {
        "offset": last_update_id + 1,
        "timeout": 3,
        "allowed_updates": ["message", "callback_query"],
    })
    if not result.get("ok"):
        return
    for update in result.get("result", []):
        last_update_id = update["update_id"]
        if "callback_query" in update:
            handle_callback(update["callback_query"])
        elif "message" in update:
            handle_message(update["message"])


def signal_handler(sig, frame):
    global running
    running = False


def main():
    global running

    if not BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    if not CHAT_ID:
        print("ERROR: Set TELEGRAM_CHAT_ID")
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    me = telegram_api("getMe")
    if not me.get("ok"):
        print("ERROR: Invalid bot token")
        sys.exit(1)

    print(f"[Telegram] @{me['result']['username']} ready")
    print(f"[Telegram] Chat ID: {CHAT_ID}")
    send_message("🟢 <b>Bot started</b> — send /help")

    while running:
        try:
            poll_updates()
            poll_for_approvals()
            poll_agent_completion()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Telegram] Error: {e}")
            time.sleep(5)

    print("[Telegram] Stopped.")


if __name__ == "__main__":
    main()
