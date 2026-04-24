---
name: deploy-savebot
description: |
  Deploy SaveBot to production server (Oracle Cloud). Runs tests, commits, pushes,
  SSH deploys, and verifies via logs. Use when code changes need to go live.
  Do NOT use for local testing or development.
disable-model-invocation: true
---

# Deploy SaveBot

## Steps

### 1. Run tests
```bash
cd "C:\Users\Timmy\Claude Projects\Telegram-Info-Bot"
python -m pytest tests/ -x -q
```
If any test fails — STOP. Fix first, then retry.

### 2. Check for uncommitted changes
```bash
git status
```
If there are changes — commit them with a descriptive message.

### 3. Push to origin
```bash
git push origin main
```

### 4. SSH Deploy
```bash
SSH_KEY="/c/Users/Timmy/Downloads/ssh-key-2026-03-04.key"
ssh -i "$SSH_KEY" ubuntu@151.145.86.66 "cd /opt/savebot && sudo systemctl stop savebot && git pull origin main && source venv/bin/activate && pip install -q -r requirements.txt && sudo systemctl start savebot"
```

### 5. Verify
Wait 5 seconds, then check logs:
```bash
SSH_KEY="/c/Users/Timmy/Downloads/ssh-key-2026-03-04.key"
ssh -i "$SSH_KEY" ubuntu@151.145.86.66 "sleep 5 && sudo journalctl -u savebot -n 15 --no-pager"
```

Look for: "Bot started" or similar success message. No tracebacks or errors.

### 6. Report
Tell the user:
- Tests: passed/failed
- Deploy: success/failure
- Last 5 log lines

## Gotchas
- NEVER run the bot locally — causes polling conflicts with the server instance
- If `git pull` fails on server — check for uncommitted changes on server
- If bot won't start — check logs for import errors or missing env vars
