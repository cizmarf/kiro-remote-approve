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
from core.cdp import do_click, get_ws_url, check_pending_approval

# Load environment
load_env()

# === Configuration ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# === State ===
last_update_id = 0
running = True
last_notified_command = None


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
    text = message.get("text", "").strip().lower()
    from_user = str(message.get("from", {}).get("id", ""))

    if from_user != str(CHAT_ID):
        return

    if text in ("/start", "/help"):
        send_message(
            "🤖 <b>Kiro Remote Approve</b>\n\n"
            "Commands:\n"
            "  <b>y</b> / <b>yes</b> → Run (approve)\n"
            "  <b>n</b> / <b>no</b> → Reject\n"
            "  <b>t</b> / <b>trust</b> → Trust (always approve)\n"
            "  /buttons → Show buttons\n"
            "  /status → Check Kiro connection"
        )
    elif text in ("y", "yes", "ok", "go", "/approve", "run"):
        result = do_click("approve")
        send_message(result)
    elif text in ("n", "no", "nope", "stop", "/reject"):
        result = do_click("reject")
        send_message(result)
    elif text in ("t", "trust", "always", "/trust"):
        result = do_click("trust")
        send_message(result)
    elif text == "/buttons":
        send_message("🤖 <b>Approve?</b>", reply_markup={
            "inline_keyboard": [[
                {"text": "✅ Run", "callback_data": "approve"},
                {"text": "❌ Reject", "callback_data": "reject"},
                {"text": "🔄 Trust", "callback_data": "trust"},
            ]]
        })
    elif text == "/status":
        ws = get_ws_url()
        if ws:
            send_message("🟢 <b>Kiro is connected</b>")
        else:
            send_message(
                "🔴 <b>Cannot reach Kiro</b>\n\n"
                "Make sure it's running with "
                "--remote-debugging-port=9229"
            )
    else:
        send_message("❓ Send <b>y</b>, <b>n</b>, <b>t</b>, or /help")


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
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Telegram] Error: {e}")
            time.sleep(5)

    print("[Telegram] Stopped.")


if __name__ == "__main__":
    main()
