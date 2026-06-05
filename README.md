# Kiro Remote Approve

Approve or reject Kiro IDE agent commands from your phone via **Telegram** or **Slack**.

When Kiro's AI agent wants to run a tool (file write, shell command, etc.), it pauses and waits for your approval. This project lets you tap a button on your messaging app instead of switching to your computer.

## How It Works

```
┌──────────────┐   Telegram API   ┌─────────────────┐   CDP/WebSocket  ┌──────────┐
│  Your Phone  │◀────────────────▶│  telegram-bot/  │──────────────────▶│  Kiro    │
│  (Telegram)  │                  │  bot.py         │                  │  IDE     │
└──────────────┘                  └────────┬────────┘                  └──────────┘
                                           │
┌──────────────┐   Slack Socket   ┌────────┴────────┐
│  Slack       │◀────────────────▶│  slack-bot/     │
│  (Desktop/   │   Mode (WSS)    │  bot.py         │
│   Mobile)    │                  └─────────────────┘
└──────────────┘
                                     Shared core/
                                     ├── cdp.py (CDP click logic)
                                     └── config.py (env, selectors)
```

Both bots share the same CDP core that connects to Kiro's Chrome DevTools Protocol debug port, finds the agent webview iframe, and programmatically clicks the approval buttons.

## Features

- **Two integrations**: Telegram and Slack (run one or both)
- **Interactive buttons**: Tap to approve, reject, or trust (both platforms)
- **Text commands**: `y` / `n` / `t` (case-insensitive — `Y`, `Yes`, `GO` all work)
- **Auto-notifications**: Detects pending approvals and sends you a message with details
- **Slack Socket Mode**: No public URL needed — works from your phone anywhere
- **Standalone CLI**: `cdp-click.py` works independently for scripting

## Prerequisites

- **Kiro IDE** launched with `--remote-debugging-port=9229`
- **Python 3.8+**

## Setup

### 1. Launch Kiro with CDP enabled

```bash
kiro --remote-debugging-port=9229
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Copy `.env.example` to `.env` and fill in the values for your chosen integration.

---

## Telegram Setup

1. Message [@BotFather](https://t.me/botfather) → `/newbot` → save the token
2. Message [@userinfobot](https://t.me/userinfobot) → get your chat ID
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
4. Run:

```bash
python3 telegram-bot/bot.py
```

### Telegram commands

| Input | Action |
|-------|--------|
| `y`, `yes`, `ok`, `go`, `run` | Approve |
| `n`, `no`, `nope`, `stop` | Reject |
| `t`, `trust`, `always` | Trust (always approve) |
| `/buttons` | Show inline button keyboard |
| `/status` | Check Kiro connection |
| `/help` | Show help |

---

## Slack Setup

### 1. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Under **OAuth & Permissions**, add Bot Token Scopes:
   - `chat:write` — send messages
   - `im:history` — read DM messages
   - `im:write` — open DMs
3. Install the app to your workspace and copy the **Bot User OAuth Token** (`xoxb-...`)

### 2. Enable Socket Mode

1. Under **Socket Mode**, toggle it on
2. Under **Basic Information → App-Level Tokens**, create a token with `connections:write` scope
3. Copy the **App-Level Token** (`xapp-...`)

### 3. Subscribe to Events

1. Under **Event Subscriptions**, enable events
2. Subscribe to bot events: `message.im`

### 4. Enable Interactivity

1. Under **Interactivity & Shortcuts**, toggle Interactivity on
   (No Request URL needed — Socket Mode handles it)

### 5. Configure environment

Set in `.env`:
- `SLACK_BOT_TOKEN` — the `xoxb-...` token
- `SLACK_APP_TOKEN` — the `xapp-...` token
- `SLACK_USER_ID` — your Slack user ID (click your profile → "..." → Copy member ID)

### 6. Run

```bash
python3 slack-bot/bot.py
```

### Slack commands

Type in the DM with the bot:

| Input | Action |
|-------|--------|
| `y`, `yes`, `ok`, `go`, `run` | Approve |
| `n`, `no`, `nope`, `stop` | Reject |
| `t`, `trust`, `always` | Trust |
| `status` | Check Kiro connection |
| `help` | Show help |

Interactive buttons (✅ Run / ❌ Reject / 🔄 Trust) appear automatically when an approval is pending.

---

## Standalone CLI

`cdp-click.py` works without any messaging integration:

```bash
python3 cdp-click.py approve   # Click "Run"
python3 cdp-click.py reject    # Click "Reject"
python3 cdp-click.py trust     # Click "Trust"
```

## Project Structure

```
kiro-remote-approve/
├── core/
│   ├── __init__.py         # Package exports
│   ├── cdp.py              # Shared CDP click logic
│   └── config.py           # Environment loading, selectors
├── telegram-bot/
│   └── bot.py              # Telegram integration
├── slack-bot/
│   └── bot.py              # Slack integration (Socket Mode + buttons)
├── cdp-click.py            # Standalone CLI tool
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

## Environment Variables

| Variable | Used By | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Telegram | Your numeric chat ID |
| `SLACK_BOT_TOKEN` | Slack | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack | App-Level Token (`xapp-...`) for Socket Mode |
| `SLACK_USER_ID` | Slack | Your Slack member ID |
| `CDP_PORT` | Both | Kiro's debug port (default: 9229) |

## Known Limitations

- Kiro must be launched with `--remote-debugging-port=9229`
- The DOM selectors may break if Kiro updates its UI
- Only one approval can be pending at a time
- Polling adds ~3 seconds delay before notification

## License

MIT — see [LICENSE](LICENSE)
