"""
CDP (Chrome DevTools Protocol) logic for clicking Kiro approval buttons.

This module is shared between all bot integrations (Telegram, Slack, etc.).
"""

import sys
import json
import asyncio
import urllib.request

from core.config import CDP_PORT, SELECTORS


def get_ws_url():
    """Find the kiroAgent webview iframe."""
    try:
        data = urllib.request.urlopen(
            f"http://127.0.0.1:{CDP_PORT}/json"
        ).read()
    except Exception:
        return None
    pages = json.loads(data)
    for p in pages:
        url = p.get("url", "")
        if p.get("type") == "iframe" and "kiroAgent" in url:
            return p["webSocketDebuggerUrl"]
    for p in pages:
        if p.get("type") == "iframe":
            return p["webSocketDebuggerUrl"]
    return None


async def _ensure_websockets():
    """Import websockets, installing if needed."""
    try:
        import websockets
        return websockets
    except ImportError:
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "websockets", "-q"]
        )
        import websockets
        return websockets


async def cdp_eval(ws_url, js):
    """Evaluate JS via CDP and return the result value."""
    websockets = await _ensure_websockets()

    async with websockets.connect(ws_url) as ws:
        msg = json.dumps({
            "id": 99,
            "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True}
        })
        await ws.send(msg)
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        return resp.get("result", {}).get("result", {}).get("value")


async def cdp_click(action):
    """
    Click a Kiro approval button via CDP WebSocket.

    Returns a human-readable result string.
    """
    websockets = await _ensure_websockets()

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
            resp = json.loads(
                await asyncio.wait_for(ws.recv(), timeout=5)
            )
            result = (
                resp.get("result", {})
                .get("result", {})
                .get("value", "UNKNOWN")
            )
            if "CLICKED" in result:
                return f"✅ {action.capitalize()}d"
            elif result == "NO_BUTTON":
                return "⚠️ No pending approval found"
            else:
                return f"❓ {result}"
    except Exception as e:
        return f"❌ CDP error: {e}"


def do_click(action):
    """Synchronous wrapper for cdp_click."""
    return asyncio.run(cdp_click(action))


def check_pending_approval():
    """
    Poll Kiro via CDP to detect pending approval.

    Returns the command text if a new approval is pending, None otherwise.
    """
    ws_url = get_ws_url()
    if not ws_url:
        return None

    js = """
    (function() {
        const snackbar = document.querySelector('.kiro-snackbar-container.needs-attention');
        if (!snackbar) {
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
        const cmds = document.querySelectorAll('.agent-outcome-details pre');
        const cmd = cmds.length > 0 ? cmds[cmds.length - 1] : null;
        return cmd ? cmd.textContent : 'PENDING_NO_CMD';
    })()
    """

    try:
        result = asyncio.run(cdp_eval(ws_url, js))
        return result
    except Exception:
        return None
