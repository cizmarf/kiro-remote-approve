#!/usr/bin/env python3
"""
Click Kiro approval buttons via Chrome DevTools Protocol.
Requires Kiro launched with --remote-debugging-port=9229

Usage:
  python3 cdp-click.py approve   # Click "Run"
  python3 cdp-click.py reject    # Click "Reject"
  python3 cdp-click.py trust     # Click "Trust"
"""

import sys
import json
import asyncio
import urllib.request

CDP_PORT = 9229
CDP_URL = f"http://127.0.0.1:{CDP_PORT}/json"

SELECTORS = {
    "approve": '.kiro-snackbar-actions button[data-variant="primary"]',
    "reject": '.kiro-snackbar-actions button[data-variant="tertiary"]',
    "trust": '.kiro-snackbar-actions button[data-variant="secondary"]',
}


def get_ws_url():
    """Find the kiroAgent webview iframe (where the snackbar lives)."""
    data = urllib.request.urlopen(CDP_URL).read()
    pages = json.loads(data)
    # Target the kiroAgent iframe
    for p in pages:
        url = p.get("url", "")
        if p.get("type") == "iframe" and "kiroAgent" in url:
            print(f"  → Targeting: {p.get('title', '')[:60]}")
            return p["webSocketDebuggerUrl"]
    # Fallback: any iframe
    for p in pages:
        if p.get("type") == "iframe":
            print(f"  → Targeting (fallback): {p.get('title', '')[:60]}")
            return p["webSocketDebuggerUrl"]
    raise RuntimeError("Cannot find Kiro chat webview iframe")


async def click_button(action: str):
    """Connect via WebSocket and click the button."""
    try:
        import websockets
    except ImportError:
        print("Installing websockets...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    ws_url = get_ws_url()
    selector = SELECTORS[action]

    # Use simple .click() — same as what worked in DevTools Console
    # First, try to find the button, dumping DOM info for debugging
    js = f"""
    (function() {{
        const btn = document.querySelector('{selector}');
        if (btn) {{
            btn.click();
            return 'CLICKED';
        }}
        // Try inside nested iframes
        const iframes = document.querySelectorAll('iframe');
        for (let i = 0; i < iframes.length; i++) {{
            try {{
                const doc = iframes[i].contentDocument;
                if (doc) {{
                    const innerBtn = doc.querySelector('{selector}');
                    if (innerBtn) {{
                        innerBtn.click();
                        return 'CLICKED_IN_IFRAME_' + i;
                    }}
                }}
            }} catch(e) {{}}
        }}
        // Debug: what DO we see?
        const body = document.body ? document.body.innerHTML.slice(0, 500) : 'NO_BODY';
        return 'NO_BUTTON|iframes=' + iframes.length + '|body=' + body;
    }})()
    """

    async with websockets.connect(ws_url) as ws:
        msg = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True}
        })
        await ws.send(msg)
        resp = json.loads(await ws.recv())
        result = resp.get("result", {}).get("result", {}).get("value", "UNKNOWN")
        if result == "CLICKED":
            print(f"✅ {action.capitalize()}d successfully")
        elif result == "NO_BUTTON":
            print("⚠️  No approval button found (nothing pending?)")
        else:
            print(f"❓ Result: {result}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in SELECTORS:
        print("Usage: python3 cdp-click.py [approve|reject|trust]")
        sys.exit(1)

    action = sys.argv[1]
    asyncio.run(click_button(action))


if __name__ == "__main__":
    main()
