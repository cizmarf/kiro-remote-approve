"""
CDP (Chrome DevTools Protocol) logic for clicking Kiro approval buttons.

This module is shared between all bot integrations (Telegram, Slack, etc.).
"""

import sys
import json
import asyncio
import urllib.request

from core.config import (
    CDP_PORT, SELECTORS,
    CHAT_INPUT_SELECTOR, CHAT_INPUT_FALLBACKS,
    CHAT_SUBMIT_SELECTOR,
    AGENT_OUTPUT_SELECTOR, AGENT_OUTPUT_FALLBACKS,
)


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


async def cdp_eval_async(ws_url, js):
    """Evaluate JS via CDP with awaitPromise (for async/Promise results)."""
    websockets = await _ensure_websockets()

    async with websockets.connect(ws_url) as ws:
        msg = json.dumps({
            "id": 99,
            "method": "Runtime.evaluate",
            "params": {
                "expression": js,
                "returnByValue": True,
                "awaitPromise": True,
            }
        })
        await ws.send(msg)
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
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


def _build_find_input_js():
    """Build JS to find the chat input contenteditable div."""
    selectors = [CHAT_INPUT_SELECTOR] + CHAT_INPUT_FALLBACKS
    checks = ""
    for sel in selectors:
        checks += f"""
        el = doc.querySelector('{sel}');
        if (el) return {{ found: true, selector: '{sel}', inIframe: inIframe }};
"""
    return f"""
    (function() {{
        function search(doc, inIframe) {{
            let el;
            {checks}
            return null;
        }}
        let result = search(document, false);
        if (result) return result;
        const iframes = document.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {{
            try {{
                const doc = iframes[i].contentDocument;
                if (doc) {{
                    result = search(doc, true);
                    if (result) return result;
                }}
            }} catch(e) {{}}
        }}
        return {{ found: false }};
    }})()
    """


def _build_send_message_js(text, selector):
    """Build JS to type text into ProseMirror contenteditable and click submit."""
    # Escape text for JS string
    escaped = (text
               .replace("\\", "\\\\")
               .replace("'", "\\'")
               .replace("\n", "\\n")
               .replace("\r", ""))
    submit_sel = CHAT_SUBMIT_SELECTOR
    return f"""
    (function() {{
        function findInDoc(doc) {{
            const input = doc.querySelector('{selector}');
            if (!input) return null;
            return {{ input: input, doc: doc }};
        }}
        function doSend(input, doc) {{
            // Focus the contenteditable
            input.focus();
            // Clear existing content and set new text
            input.innerHTML = '<p>{escaped}</p>';
            // Dispatch input event so ProseMirror picks it up
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            // Wait a tick for the submit button to enable, then click it
            return new Promise(resolve => {{
                setTimeout(() => {{
                    const btn = doc.querySelector('{submit_sel}');
                    if (btn) {{
                        btn.removeAttribute('disabled');
                        btn.click();
                        resolve('SENT');
                    }} else {{
                        resolve('NO_SUBMIT_BTN');
                    }}
                }}, 150);
            }});
        }}
        let found = findInDoc(document);
        if (found) return doSend(found.input, found.doc);
        const iframes = document.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {{
            try {{
                const doc = iframes[i].contentDocument;
                if (doc) {{
                    found = findInDoc(doc);
                    if (found) return doSend(found.input, found.doc);
                }}
            }} catch(e) {{}}
        }}
        return 'NO_INPUT';
    }})()
    """


def _build_get_agent_output_js(max_lines=10):
    """Build JS to get the last agent response text."""
    selectors = [AGENT_OUTPUT_SELECTOR] + AGENT_OUTPUT_FALLBACKS
    checks = ""
    for sel in selectors:
        checks += f"""
        els = doc.querySelectorAll('{sel}');
        if (els.length > 0) {{
            const last = els[els.length - 1];
            return last.innerText || last.textContent || '';
        }}
"""
    return f"""
    (function() {{
        function search(doc) {{
            let els;
            {checks}
            return null;
        }}
        let result = search(document);
        if (result) {{
            const lines = result.split('\\n');
            return lines.slice(-{max_lines}).join('\\n');
        }}
        const iframes = document.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {{
            try {{
                const doc = iframes[i].contentDocument;
                if (doc) {{
                    result = search(doc);
                    if (result) {{
                        const lines = result.split('\\n');
                        return lines.slice(-{max_lines}).join('\\n');
                    }}
                }}
            }} catch(e) {{}}
        }}
        return null;
    }})()
    """


def _build_check_agent_busy_js():
    """Build JS to check if the agent is currently processing."""
    return """
    (function() {
        function check(doc) {
            // Look for stop button or spinner indicating agent is working
            const stopBtn = doc.querySelector('[class*="stop"]');
            if (stopBtn) return true;
            const spinner = doc.querySelector('[class*="spinner"]');
            if (spinner) return true;
            const thinking = doc.querySelector('[class*="thinking"]');
            if (thinking) return true;
            return false;
        }
        if (check(document)) return true;
        const iframes = document.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {
            try {
                const doc = iframes[i].contentDocument;
                if (doc && check(doc)) return true;
            } catch(e) {}
        }
        return false;
    })()
    """


async def cdp_send_message(text):
    """
    Type a message into the Kiro agent chat input and submit it.

    Returns a human-readable result string.
    """
    await _ensure_websockets()

    ws_url = get_ws_url()
    if not ws_url:
        return "ERROR: Cannot find Kiro webview"

    # First, find which selector works
    find_js = _build_find_input_js()
    try:
        find_result = await cdp_eval(ws_url, find_js)
    except Exception as e:
        return f"❌ CDP error finding input: {e}"

    if not find_result or not find_result.get("found"):
        return "⚠️ Cannot find chat input (is the chat panel open?)"

    selector = find_result["selector"]

    # Now send the message (uses awaitPromise since setTimeout)
    send_js = _build_send_message_js(text, selector)
    try:
        result = await cdp_eval_async(ws_url, send_js)
        if result == "SENT":
            return "📨 Sent to agent"
        elif result == "NO_SUBMIT_BTN":
            return "⚠️ Cannot find submit button"
        elif result == "NO_INPUT":
            return "⚠️ Chat input disappeared"
        else:
            return f"❓ {result}"
    except Exception as e:
        return f"❌ CDP error: {e}"


def send_message_to_agent(text):
    """Synchronous wrapper for cdp_send_message."""
    return asyncio.run(cdp_send_message(text))


async def cdp_get_agent_output(max_lines=10):
    """Get the last few lines of the agent's latest response."""
    ws_url = get_ws_url()
    if not ws_url:
        return None

    js = _build_get_agent_output_js(max_lines)
    try:
        return await cdp_eval(ws_url, js)
    except Exception:
        return None


def get_agent_output(max_lines=10):
    """Synchronous wrapper for cdp_get_agent_output."""
    return asyncio.run(cdp_get_agent_output(max_lines))


async def cdp_is_agent_busy():
    """Check if the agent is currently processing (has stop button/spinner)."""
    ws_url = get_ws_url()
    if not ws_url:
        return False

    js = _build_check_agent_busy_js()
    try:
        return await cdp_eval(ws_url, js)
    except Exception:
        return False


def is_agent_busy():
    """Synchronous wrapper for cdp_is_agent_busy."""
    return asyncio.run(cdp_is_agent_busy())
