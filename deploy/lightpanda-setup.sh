#!/bin/bash
# Lightpanda Browser — setup script for OpenClaw agent (Hetzner CX33)
# Usage: ssh root@178.104.30.181 "bash -s" < deploy/lightpanda-setup.sh
#
# What it does:
#   1. Downloads Lightpanda binary
#   2. Installs the agent-skill for OpenClaw
#   3. Configures OpenClaw browser profile (remote CDP)
#   4. Creates systemd service for Lightpanda
#   5. Restarts OpenClaw gateway

set -euo pipefail

APP_USER="openclaw"
OPENCLAW_HOME="/home/${APP_USER}/.openclaw"
LIGHTPANDA_BIN="/usr/local/bin/lightpanda"
LIGHTPANDA_PORT=9222

echo "=== Lightpanda Browser Setup for OpenClaw ==="

# ── 1. Download Lightpanda binary ─────────────────────────
echo "[1/5] Downloading Lightpanda binary..."
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    BINARY_URL="https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux"
elif [ "$ARCH" = "aarch64" ]; then
    BINARY_URL="https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-aarch64-linux"
else
    echo "ERROR: Unsupported architecture: $ARCH"
    exit 1
fi

curl -L -o "${LIGHTPANDA_BIN}" "${BINARY_URL}"
chmod +x "${LIGHTPANDA_BIN}"
echo "  Installed: ${LIGHTPANDA_BIN}"
${LIGHTPANDA_BIN} --version 2>/dev/null || echo "  (version check not supported)"

# ── 2. Install agent-skill ────────────────────────────────
echo "[2/5] Installing Lightpanda agent skill..."
SKILLS_DIR="${OPENCLAW_HOME}/skills"
sudo -u "${APP_USER}" mkdir -p "${SKILLS_DIR}"

if [ -d "${SKILLS_DIR}/lightpanda" ]; then
    echo "  Skill already exists, updating..."
    cd "${SKILLS_DIR}/lightpanda"
    sudo -u "${APP_USER}" git pull origin main 2>/dev/null || true
else
    sudo -u "${APP_USER}" git clone \
        https://github.com/lightpanda-io/agent-skill.git \
        "${SKILLS_DIR}/lightpanda"
fi

# Run install script if present (downloads binary to skill dir too)
if [ -f "${SKILLS_DIR}/lightpanda/scripts/install.sh" ]; then
    echo "  Running skill install script..."
    cd "${SKILLS_DIR}/lightpanda"
    sudo -u "${APP_USER}" bash scripts/install.sh || true
fi

echo "  Skill installed at: ${SKILLS_DIR}/lightpanda"

# ── 3. Configure OpenClaw browser profile ─────────────────
echo "[3/5] Configuring OpenClaw browser profile..."
OPENCLAW_CONFIG="${OPENCLAW_HOME}/openclaw.json"

if [ -f "${OPENCLAW_CONFIG}" ]; then
    # Check if browser config already exists
    if python3 -c "
import json, sys
with open('${OPENCLAW_CONFIG}') as f:
    cfg = json.load(f)
if 'browser' in cfg and cfg['browser'].get('profiles', {}).get('lightpanda'):
    print('already configured')
    sys.exit(0)

# Add browser config
cfg.setdefault('browser', {})
cfg['browser']['enabled'] = True
cfg['browser'].setdefault('profiles', {})
cfg['browser']['profiles']['lightpanda'] = {
    'cdpUrl': 'ws://127.0.0.1:${LIGHTPANDA_PORT}'
}
# Set as default profile
cfg['browser']['defaultProfile'] = 'lightpanda'

with open('${OPENCLAW_CONFIG}', 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print('configured')
" 2>/dev/null; then
        echo "  Browser profile configured in openclaw.json"
    else
        echo "  WARNING: Could not auto-configure. Add manually to ${OPENCLAW_CONFIG}:"
        echo '  "browser": { "enabled": true, "defaultProfile": "lightpanda", "profiles": { "lightpanda": { "cdpUrl": "ws://127.0.0.1:9222" } } }'
    fi
else
    echo "  WARNING: ${OPENCLAW_CONFIG} not found. Configure browser profile manually after OpenClaw setup."
fi

# ── 4. Create systemd service ─────────────────────────────
echo "[4/5] Creating systemd service for Lightpanda..."
cat > /etc/systemd/system/lightpanda.service <<UNIT
[Unit]
Description=Lightpanda Headless Browser (CDP on port ${LIGHTPANDA_PORT})
After=network.target
Before=openclaw-watchdog.service

[Service]
Type=simple
ExecStart=${LIGHTPANDA_BIN} serve --host 127.0.0.1 --port ${LIGHTPANDA_PORT}
Restart=always
RestartSec=3
User=${APP_USER}

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable lightpanda
systemctl start lightpanda

echo "  Service started on 127.0.0.1:${LIGHTPANDA_PORT}"

# ── 5. Restart OpenClaw gateway ───────────────────────────
echo "[5/5] Restarting OpenClaw gateway..."
# Try multiple restart methods
if sudo -u "${APP_USER}" openclaw gateway restart 2>/dev/null; then
    echo "  Gateway restarted via CLI"
elif systemctl restart openclaw-watchdog 2>/dev/null; then
    echo "  Gateway restarted via systemd"
else
    echo "  WARNING: Could not auto-restart gateway. Run manually:"
    echo "    sudo -u ${APP_USER} openclaw gateway restart"
fi

# ── Verify ────────────────────────────────────────────────
echo ""
echo "=== Verification ==="
echo -n "Lightpanda service: "
systemctl is-active lightpanda 2>/dev/null || echo "not running"

echo -n "CDP endpoint: "
if curl -s http://127.0.0.1:${LIGHTPANDA_PORT}/json/version 2>/dev/null | head -1; then
    echo ""
else
    echo "not responding (may need a few seconds to start)"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Lightpanda is running on ws://127.0.0.1:${LIGHTPANDA_PORT}"
echo ""
echo "Commands:"
echo "  Status:  systemctl status lightpanda"
echo "  Logs:    journalctl -u lightpanda -f"
echo "  Restart: systemctl restart lightpanda"
echo ""
echo "Limitations:"
echo "  - No screenshots/PDF (text + accessibility tree only)"
echo "  - Use DuckDuckGo, not Google (fingerprint blocking)"
echo "  - 1 CDP connection per process"
echo ""
echo "Test in OpenClaw TUI:"
echo "  sudo -u ${APP_USER} openclaw tui"
echo '  > "Open https://example.com and tell me what you see"'
