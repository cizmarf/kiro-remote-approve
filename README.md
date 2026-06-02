# Kiro Remote Approve

Approve or reject Kiro IDE agent commands from your phone via Telegram.

When Kiro's AI agent wants to run a tool (file write, shell command, etc.), it pauses and waits for your approval. This project lets you tap a button on Telegram instead of switching to your computer.

## How It Works

The bot connects to Kiro's Chrome DevTools Protocol (CDP) debug port, finds the agent webview iframe, and programmatically clicks the approval buttons in the DOM — the same as if you clicked them yourself.

```
┌──────────────┐   Telegram API   ┌─────────────────┐   CDP/WebSocket  ┌──────────┐
│  Your Phone  │◀──────────────-─▶│  bot.py         │──────────-──────▶│  Kiro    │
│  (Telegram)  │                  │  (local)        │                  │  IDE     │
└──────────────┘                  └─────────────────┘                  └──────────┘
                                         │
                                         │ polls for pending
                                         │ approvals & notifies
                                         ▼
                                  Auto-detects when Kiro
                                  is waiting for input
```

## Features

- **Text commands**: `y` / `n` / `t` to approve, reject, or trust
- **Inline buttons**: Tap ✅ Run, ❌ Reject, or 🔄 Trust
- **Auto-notifications**: Bot detects pending approvals and sends you a message with the command details
- **Standalone CLI**: `cdp-click.py` works independently for scripting

## Prerequisites

- **Kiro IDE** launched with `--remote-debugging-port=9229`
- **Python 3.8+**
- **websockets** pip package
- A **Telegram bot** (free, takes 30 seconds to create)

## Setup

### 1. Launch Kiro with CDP enabled

```bash
kiro --remote-debugging-port=9229
```

You must have just a single Kiro window open.

### 2. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot`, follow the prompts
3. Save the bot token (looks like `123456789:AAH...`)

### 3. Get your Telegram chat ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send `/start` — it replies with your numeric chat ID

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure and run

Set up `.env` or

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"

python3 telegram-bot/bot.py
```

Or copy `.env.example` to `.env` and source it before running.

## Usage

### Telegram commands

| Input | Action |
|-------|--------|
| `y`, `yes`, `ok`, `go`, `run` | Approve (click Run) |
| `n`, `no`, `nope`, `stop` | Reject |
| `t`, `trust`, `always` | Trust (always approve) |
| `/buttons` | Show inline button keyboard |
| `/status` | Check if Kiro is reachable via CDP |
| `/help` | Show help |

### Auto-notifications

The bot polls Kiro every few seconds. When it detects a pending approval, it sends you a Telegram message with:
- The command/tool waiting for approval
- Inline buttons to approve, reject, or trust

### Standalone CLI tool

`cdp-click.py` works without Telegram — useful for scripts or keybindings:

```bash
python3 cdp-click.py approve   # Click "Run"
python3 cdp-click.py reject    # Click "Reject"
python3 cdp-click.py trust     # Click "Trust"
```

### Auto-start the bot (macOS LaunchAgent)

Create `~/Library/LaunchAgents/com.kiro.remote-approve.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kiro.remote-approve</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/kiro-remote-approve/telegram-bot/bot.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TELEGRAM_BOT_TOKEN</key>
        <string>your-bot-token</string>
        <key>TELEGRAM_CHAT_ID</key>
        <string>your-chat-id</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.kiro.remote-approve.plist
```

## Project Structure

```
kiro-remote-approve/
├── telegram-bot/
│   └── bot.py              # Main bot — Telegram + CDP integration
├── cdp-click.py            # Standalone CLI tool
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── LICENSE                 # MIT
└── README.md
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your numeric Telegram user/chat ID |
| `CDP_PORT` | No | Kiro's debug port (default: `9229`) |

## Known Limitations

- Kiro must be launched with `--remote-debugging-port=9229` every time
- If Kiro restarts, the CDP WebSocket URL changes (bot reconnects automatically on next poll)
- The DOM selectors (`.kiro-snackbar-actions button[data-variant="..."]`) may break if Kiro updates its UI
- Only one approval can be pending at a time (Kiro's limitation, not the bot's)
- Auto-detection polling adds a small delay (~3-5 seconds) before you get notified

## License

MIT — see [LICENSE](LICENSE)
