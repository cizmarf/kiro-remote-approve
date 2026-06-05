"""Shared configuration and environment loading."""

import os
from pathlib import Path

# === Button selectors ===
SELECTORS = {
    "approve": '.kiro-snackbar-actions button[data-variant="primary"]',
    "reject": '.kiro-snackbar-actions button[data-variant="tertiary"]',
    "trust": '.kiro-snackbar-actions button[data-variant="secondary"]',
}

# === Chat selectors ===
# The chat input is a ProseMirror contenteditable div
CHAT_INPUT_SELECTOR = '.tiptap.ProseMirror[contenteditable="true"]'
# Fallback selectors to try for the chat input
CHAT_INPUT_FALLBACKS = [
    '[contenteditable="true"].ProseMirror',
    '.ProseMirror[contenteditable="true"]',
]
# The submit button
CHAT_SUBMIT_SELECTOR = 'button.kiro-button[data-variant="submit"]'
# The agent's response text (last message from the assistant)
AGENT_OUTPUT_SELECTOR = '.message-body .markdown-body'
# Fallback selectors for agent output
AGENT_OUTPUT_FALLBACKS = [
    '.assistant-message .markdown-body',
    '[class*="assistant"] .markdown-body',
    '.message-content',
    '[class*="message"] [class*="markdown"]',
]

CDP_PORT = int(os.environ.get("CDP_PORT", "9229"))


def load_env():
    """Load .env file from project root if present."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    # Re-read CDP_PORT after loading env
    global CDP_PORT
    CDP_PORT = int(os.environ.get("CDP_PORT", "9229"))
