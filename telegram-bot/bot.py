#!/usr/bin/env python3
"""
Kiro Remote Approve - Telegram Bot via CDP

Approve/reject Kiro agent commands from your phone via Telegram.
Requires Kiro launched with: --remote-debugging-port=9229

Usage:
  python3 bot.py

Environment variables (or edit below):
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Your chat ID from @userinfobot
"""

import os
import sys
import json
import time
import signal
import asyncio
import urllib.request
import urllib.error
from pathlib import Path

# === Load .env if present ===
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# === Configuration ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CDP_PORT = int(os.environ.get("CDP_PORT", "9229"))

# === State ===
last_update_id = 0
running = True
last_notified_command = None  # Track to avoid duplicate notifications

# === Button selectors ===
SELECTORS = {
    "approve": '.kiro-snackbar-actions button[data-variant="primary"]',
    "reject": '.kiro-snackbar-actions button[data-variant="tertiary"]',
    "trust": '.kiro-snackbar-actions button[data-variant="secondary"]',
}


# === Telegram API ===
def telegram_api(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
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


# === CDP Click Logic ===
def get_ws_url():
    """Find the kiroAgent webview iframe."""
    data = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read()
    pages = json.loads(data)
    for p in pages:
        url = p.get("url", "")
        if p.get("type") == "iframe" and "kiroAgent" in url:
            return p["webSocketDebuggerUrl"]
    for p in pages:
        if p.get("type") == "iframe":
            return p["webSocketDebuggerUrl"]
    return None


async def cdp_click(action):
    """Click a Kiro approval button via CDP WebSocket."""
    try:
        import websockets
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    ws_url = get_ws_url()
    if not ws_url:
        return "ERROR: Cannot find Kiro webview (is Kiro running with --remote-debugging-port=9229?)"

    selector = SELECTORS[action]
    js = f"""
    (function() {{
        const btn = document.querySelector('{selector}');
        if (btn) {{ btn.click(); return 'CLICKED'; }}
        const iframes = document.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {{
            try {{
                const doc = iframes[i].contentDocument;
                if (doc) {{
                    const innerBtn = doc.querySelector('{selector}');
                    if (innerBtn) {{ innerBtn.click(); return 'CLICKED_IFRAME'; }}
                }}
            }} catch(e) {{}}
        }}
        return 'NO_BUTTON';
    }})()
    """

    try:
        async with websockets.connect(ws_url) as ws:
            msg = json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": js, "returnByValue": True}
            })
            await ws.send(msg)
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            result = resp.get("result", {}).get("result", {}).get("value", "UNKNOWN")
            if "CLICKED" in result:
                return f"✅ {action.capitalize()}d"
            elif result == "NO_BUTTON":
                return "⚠️ No pending approval found"
            else:
                return f"❓ {result}"
    except Exception as e:
        return f"❌ CDP error: {e}"


def do_click(action):
    """Synchronous wrapper for CDP click."""
    return asyncio.run(cdp_click(action))


# === Message Handlers ===
def handle_callback(callback_query):
    data = callback_query.get("data", "")
    callback_id = callback_query.get("id", "")
    from_user = str(callback_query.get("from", {}).get("id", ""))

    if from_user != str(CHAT_ID):
        telegram_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "⛔ Unauthorized", "show_alert": True})
        return

    if data in SELECTORS:
        result = do_click(data)
        telegram_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": result})
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
            "inline_keyboard": [
                [
                    {"text": "✅ Run", "callback_data": "approve"},
                    {"text": "❌ Reject", "callback_data": "reject"},
                    {"text": "🔄 Trust", "callback_data": "trust"},
                ]
            ]
        })
    elif text == "/status":
        ws = get_ws_url()
        if ws:
            send_message("🟢 <b>Kiro is connected</b>")
        else:
            send_message("🔴 <b>Cannot reach Kiro</b>\n\nMake sure it's running with --remote-debugging-port=9229")
    else:
        send_message("❓ Send <b>y</b>, <b>n</b>, <b>t</b>, or /help")


# === Approval Watcher ===
def check_pending_approval():
    """Poll Kiro via CDP to detect pending approval and extract the command."""
    global last_notified_command

    ws_url = get_ws_url()
    if not ws_url:
        return

    js = """
    (function() {
        // Check if snackbar with "Waiting on your input" is visible
        const snackbar = document.querySelector('.kiro-snackbar-container.needs-attention');
        if (!snackbar) {
            // Also check inside iframes
            const iframes = document.querySelectorAll('iframe');
            for (let i = 0; i < iframes.length; i++) {
                try {
                    const doc = iframes[i].contentDocument;
                    if (doc) {
                        const sb = doc.querySelector('.kiro-snackbar-container.needs-attention');
                        if (sb) {
                            const cmds = doc.querySelectorAll('.agent-outcome-details pre');
                            const cmd = cmds.length > 0 ? cmds[cmds.length - 1] : null;
                            return cmd ? cmd.textContent : 'PENDING_NO_CMD';
                        }
                    }
                } catch(e) {}
            }
            return null;
        }
        // Found in main doc - get the LAST command (most recent/pending one)
        const cmds = document.querySelectorAll('.agent-outcome-details pre');
        const cmd = cmds.length > 0 ? cmds[cmds.length - 1] : null;
        return cmd ? cmd.textContent : 'PENDING_NO_CMD';
    })()
    """

    try:
        result = asyncio.run(_cdp_eval(ws_url, js))
        if result and result != "null" and result != last_notified_command:
            last_notified_command = result
            cmd_text = result if result != "PENDING_NO_CMD" else "(unknown command)"
            send_message(
                f"🔔 <b>Kiro needs approval</b>\n\n<code>{cmd_text}</code>",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {"text": "✅ Run", "callback_data": "approve"},
                            {"text": "❌ Reject", "callback_data": "reject"},
                            {"text": "🔄 Trust", "callback_data": "trust"},
                        ]
                    ]
                }
            )
        elif not result:
            # No pending approval - reset tracker
            last_notified_command = None
    except Exception:
        pass


async def _cdp_eval(ws_url, js):
    """Evaluate JS via CDP and return the result value."""
    try:
        import websockets
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    async with websockets.connect(ws_url) as ws:
        msg = json.dumps({
            "id": 99,
            "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True}
        })
        await ws.send(msg)
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        return resp.get("result", {}).get("result", {}).get("value")


# === Main Loop ===
def poll_updates():
    global last_update_id
    result = telegram_api("getUpdates", {
        "offset": last_update_id + 1,
        "timeout": 3,  # Short timeout so we can check for approvals frequently
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
        print("ERROR: Set TELEGRAM_CHAT_ID (send /start to @userinfobot on Telegram)")
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    me = telegram_api("getMe")
    if not me.get("ok"):
        print("ERROR: Invalid bot token")
        sys.exit(1)

    print(f"[Bot] @{me['result']['username']} ready")
    print(f"[Bot] Chat ID: {CHAT_ID}")
    print(f"[Bot] CDP port: {CDP_PORT}")
    send_message("🟢 <b>Bot started</b> — send /help")

    while running:
        try:
            poll_updates()
            check_pending_approval()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Bot] Error: {e}")
            time.sleep(5)

    print("[Bot] Stopped.")


if __name__ == "__main__":
    main()
