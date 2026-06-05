# Development Guidelines

## Python Style

- No heavy frameworks — stdlib + `websockets` for CDP + `slack_bolt` for Slack
- Shared core logic in `core/` module (cdp.py, config.py)
- Platform-specific bots in their own directories (telegram-bot/, slack-bot/)
- Auto-load `.env` from project root (no python-dotenv dependency)
- Type hints welcome but not required
- Keep it simple — this is a hack tool, not production software

## Testing Changes

1. Launch Kiro with `--remote-debugging-port=9229`
2. Run `python3 cdp-click.py approve` to test CDP connectivity
3. Run `python3 telegram-bot/bot.py` for Telegram bot
4. Run `python3 slack-bot/bot.py` for Slack bot (Socket Mode)
5. Trigger an approval in Kiro and verify notification arrives

## CDP Notes

- The WebSocket URL changes every time Kiro restarts
- Always discover it fresh from `http://127.0.0.1:9229/json`
- Target the `iframe` type with `kiroAgent` in the URL
- `.click()` on the button works — no need for synthetic mouse events
- The bot uses a 3-second polling interval for Telegram + approval detection
- Chat input is a ProseMirror contenteditable div (`.tiptap.ProseMirror`)
- To send text: set `innerHTML`, dispatch `input` event, then click the submit button (`data-variant="submit"`)
- Agent busy detection: look for elements with `stop`/`spinner`/`thinking` in class names
- Use `awaitPromise: true` in CDP evaluate when the JS returns a Promise (e.g., setTimeout-based flows)

## Security

- Never commit `.env` — it contains the bot token
- The bot only responds to the configured `CHAT_ID`
- CDP binds to localhost only

## Adding Slack Support

Slack integration uses Socket Mode (slack_bolt):
- No public URL needed — works from phone anywhere
- Interactive buttons via Block Kit (approve/reject/trust)
- Socket Mode handles both button clicks and DM text replies
- CDP polling runs in main thread, Socket Mode in background
- Same CDP logic as Telegram, just different notification channel
