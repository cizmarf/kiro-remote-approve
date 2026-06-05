# Kiro Remote Approve

## What This Project Does

A tool that lets developers approve/reject Kiro IDE agent commands from their phone via Telegram (and soon Slack). When Kiro pauses to ask permission to run a command, the bot sends a notification with the command text and action buttons.

## How It Works

1. Kiro is launched with `--remote-debugging-port=9229`
2. A Python bot polls the Kiro webview via Chrome DevTools Protocol (CDP)
3. When a pending approval is detected (`.kiro-snackbar-container.needs-attention`), it extracts the command from the last `.agent-outcome-details pre` element
4. Sends a Telegram/Slack message with inline buttons
5. On user response, clicks the corresponding DOM button via CDP (`data-variant="primary"` for Run, `"tertiary"` for Reject, `"secondary"` for Trust)
6. Arbitrary text messages are typed into the agent chat via the ProseMirror contenteditable input and submitted by clicking the submit button
7. When the agent finishes processing, the bot sends back the last lines of the agent's response

## Key DOM Selectors

- Pending detection: `.kiro-snackbar-container.needs-attention`
- Command text: `.agent-outcome-details pre` (last one in the list)
- Run button: `.kiro-snackbar-actions button[data-variant="primary"]`
- Reject button: `.kiro-snackbar-actions button[data-variant="tertiary"]`
- Trust button: `.kiro-snackbar-actions button[data-variant="secondary"]`
- Chat input: `.tiptap.ProseMirror[contenteditable="true"]`
- Submit button: `button.kiro-button[data-variant="submit"]`

## CDP Target

The buttons live inside a cross-origin iframe (the kiroAgent webview). Target selection:
- Type: `iframe`
- URL contains: `kiroAgent`
- The button may be in a nested iframe inside that — search both the main document and child iframes.

## Project Structure

```
kiro-remote-approve/
├── core/
│   ├── __init__.py         # Package exports
│   ├── cdp.py              # Shared CDP click logic
│   └── config.py           # Environment loading, selectors
├── telegram-bot/
│   └── bot.py              # Telegram integration (HTTP polling)
├── slack-bot/
│   └── bot.py              # Slack integration (Socket Mode + buttons)
├── cdp-click.py            # Standalone CLI tool
├── requirements.txt        # websockets + slack_bolt
├── .env                    # Local secrets (gitignored)
├── .env.example            # Template for .env
├── .gitignore
├── LICENSE
└── README.md
```

## Tech Stack

- Python 3.8+ (stdlib + websockets + slack_bolt)
- Chrome DevTools Protocol via WebSocket
- Telegram Bot API (HTTP polling, no webhook)
- Slack Bot via Socket Mode (slack_bolt) — no public URL needed
