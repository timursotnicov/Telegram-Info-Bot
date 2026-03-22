# OpenClaw Server Setup Guide

Research results for setting up OpenClaw as an AI agent gateway for Telegram.

## What is OpenClaw?

OpenClaw is a self-hosted AI agent gateway that connects LLM models to messaging channels (Telegram, WhatsApp, Discord, etc.). It provides:

- **TUI** (Terminal User Interface) — chat with the agent in terminal
- **Telegram integration** — bot responds to DMs via Bot API
- **Multi-model support** — OpenRouter, OpenAI, xAI, and more
- **Agent isolation** — sandboxed workspaces per agent
- **Session management** — persistent conversation history

## Server Details

- **IP**: 178.104.30.181
- **OS**: Ubuntu (root access)
- **Version**: OpenClaw 2026.3.13 (61d171a)
- **Gateway port**: 18789 (local/loopback)

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Main config (model, gateway, channels, plugins) |
| `~/.openclaw/agents/main/agent/models.json` | Provider definitions, model catalog, API keys |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | Provider auth (API keys per provider) |
| `~/.openclaw/agents/main/sessions/` | Conversation sessions |
| `~/.openclaw/workspace/` | Agent workspace directory |

## Setup Steps

### 1. Install & Initial Setup
```bash
openclaw setup
```
- Select **Telegram (Bot API)** channel
- Enter bot token when prompted

### 2. Configure Free Model (OpenRouter)

Set the OpenRouter API key as environment variable:
```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
echo 'export OPENROUTER_API_KEY="sk-or-v1-..."' >> ~/.bashrc
```

Scan for available free models:
```bash
openclaw models scan
```

Change primary model from OpenAI to OpenRouter:
```bash
sed -i 's/"primary": "openai-codex\/gpt-5.1"/"primary": "openrouter\/nvidia\/nemotron-3-super-120b-a12b:free"/' ~/.openclaw/openclaw.json
```

Or use the interactive configure wizard:
```bash
openclaw configure
# Select "Model" → accept existing OPENROUTER_API_KEY → pick models
```

### 3. Set API Key in Agent Auth

The `auth-profiles.json` in the agent directory must contain the actual API key:
```json
{
  "openrouter": {
    "apiKey": "sk-or-v1-..."
  }
}
```

Also update `models.json` — replace the placeholder:
```bash
sed -i 's/"apiKey": "OPENROUTER_API_KEY"/"apiKey": "sk-or-v1-..."/' ~/.openclaw/agents/main/agent/models.json
```

### 4. Pair Telegram User

When a user messages the bot for the first time, they get a pairing code. Approve it:
```bash
openclaw pairing approve telegram <CODE>
```

### 5. Launch

```bash
openclaw tui          # Interactive terminal UI
openclaw gateway      # Run gateway as background service
```

## Free Models Available via OpenRouter

| Model | Speed | Context | Notes |
|-------|-------|---------|-------|
| `openrouter/openrouter/auto` | varies | 2M | Auto-selects best free model |
| `nvidia/nemotron-3-super-120b-a12b:free` | 1.7s | 256k | Best quality (120B params) |
| `nvidia/nemotron-nano-12b-v2-vl:free` | 2.2s | 125k | Vision support |
| `arcee-ai/trinity-mini:free` | 888ms | 128k | Fastest |
| `stepfun/step-3.5-flash:free` | 2.6s | 250k | Large context |

## Key Commands

```bash
openclaw setup          # Initial setup wizard
openclaw configure      # Re-configure (model, channels, etc.)
openclaw tui            # Terminal chat UI
openclaw models list    # Show configured models
openclaw models scan    # Discover available models
openclaw pairing approve telegram <CODE>  # Approve Telegram user
openclaw logs --follow  # Tail gateway logs
openclaw doctor         # Health check
openclaw status         # Channel health + recent sessions
```

## Browser Setup

Two browser engines are available for web browsing:

| Engine | Port | Use Case | Cloudflare | Speed |
|--------|------|----------|------------|-------|
| Lightpanda | 9222 | Simple sites, docs, APIs | No | Fast |
| Chromium | 9223 | JS-heavy, Cloudflare-protected | Yes | Slower |

### Install Scripts

```bash
# Lightpanda (already installed)
ssh root@178.104.30.181 "bash -s" < deploy/lightpanda-setup.sh

# Chromium fallback
ssh root@178.104.30.181 "bash -s" < deploy/chromium-fallback-setup.sh
```

### Browser Profiles in openclaw.json

```json
{
  "browser": {
    "enabled": true,
    "defaultProfile": "lightpanda",
    "profiles": {
      "lightpanda": { "cdpUrl": "ws://127.0.0.1:9222" },
      "chromium": { "cdpUrl": "ws://127.0.0.1:9223" }
    }
  }
}
```

### Service Management

```bash
# Lightpanda
systemctl status lightpanda
journalctl -u lightpanda -f

# Chromium
systemctl status chromium-openclaw
journalctl -u chromium-openclaw -f
```

## Gotchas

1. **Model config hierarchy**: Agent-level `models.json` overrides global `openclaw.json` defaults
2. **Auth format**: `auth-profiles.json` must use `{"provider": {"apiKey": "..."}}` format
3. **Telegram groupPolicy**: Set to `"open"` or add user IDs to `groupAllowFrom` to allow group messages
4. **TUI navigation**: Use `tab` to switch options, `space` to select in multi-select, arrow keys to navigate
5. **API key persistence**: Set via `openclaw configure` (Model section) — it saves to both config and agent auth
6. **Bot token**: Uses its own Telegram bot token (separate from SaveBot)
