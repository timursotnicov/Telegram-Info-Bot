#!/bin/bash
# Chromium Browser — fallback setup for OpenClaw agent (Hetzner CX33)
# Usage: ssh root@178.104.30.181 "bash -s" < deploy/chromium-fallback-setup.sh
#
# Why: Lightpanda can't bypass Cloudflare/JS-heavy sites.
# This installs Chromium as a fallback browser with CDP (Chrome DevTools Protocol).
#
# What it does:
#   1. Installs Chromium + dependencies
#   2. Creates a systemd service (headless Chromium on port 9223)
#   3. Adds "chromium" browser profile to OpenClaw config
#   4. Restarts OpenClaw gateway
#
# Port allocation:
#   - Lightpanda: 9222 (primary, fast, lightweight)
#   - Chromium:   9223 (fallback, Cloudflare-capable)

set -euo pipefail

APP_USER="openclaw"
OPENCLAW_HOME="/home/${APP_USER}/.openclaw"
CHROMIUM_PORT=9223
CHROMIUM_DATA="/home/${APP_USER}/.chromium-openclaw"

echo "=== Chromium Fallback Browser Setup for OpenClaw ==="

# ── 1. Install Chromium + dependencies ─────────────────────
echo "[1/4] Installing Chromium..."
apt update -qq
apt install -y -qq chromium-browser 2>/dev/null || apt install -y -qq chromium 2>/dev/null || {
    # Snap-based Ubuntu may need a different approach
    echo "  Trying snap install..."
    snap install chromium 2>/dev/null || {
        echo "ERROR: Could not install Chromium. Install manually:"
        echo "  apt install chromium-browser  OR  snap install chromium"
        exit 1
    }
}

# Verify installation
CHROMIUM_BIN=$(which chromium-browser 2>/dev/null || which chromium 2>/dev/null || echo "/snap/bin/chromium")
if [ ! -x "${CHROMIUM_BIN}" ]; then
    echo "ERROR: Chromium binary not found after install"
    exit 1
fi
echo "  Chromium installed: ${CHROMIUM_BIN}"
${CHROMIUM_BIN} --version

# Install common font packages for proper page rendering
apt install -y -qq fonts-liberation fonts-noto-core 2>/dev/null || true

# ── 2. Create data directory ───────────────────────────────
echo "[2/4] Creating Chromium user data directory..."
sudo -u "${APP_USER}" mkdir -p "${CHROMIUM_DATA}"

# ── 3. Create systemd service ──────────────────────────────
echo "[3/4] Creating systemd service for headless Chromium..."
cat > /etc/systemd/system/chromium-openclaw.service <<UNIT
[Unit]
Description=Headless Chromium for OpenClaw (CDP on port ${CHROMIUM_PORT})
After=network.target
Before=openclaw-watchdog.service

[Service]
Type=simple
ExecStart=${CHROMIUM_BIN} \\
    --headless=new \\
    --no-sandbox \\
    --disable-gpu \\
    --disable-dev-shm-usage \\
    --disable-software-rasterizer \\
    --remote-debugging-address=127.0.0.1 \\
    --remote-debugging-port=${CHROMIUM_PORT} \\
    --user-data-dir=${CHROMIUM_DATA} \\
    --disable-extensions \\
    --disable-background-networking \\
    --disable-sync \\
    --no-first-run \\
    --window-size=1280,720 \\
    --lang=en-US
Restart=always
RestartSec=5
User=${APP_USER}
Environment=DISPLAY=:0

# Memory limits (prevent runaway tabs)
MemoryMax=1G
MemoryHigh=768M

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable chromium-openclaw
systemctl start chromium-openclaw

echo "  Service started on 127.0.0.1:${CHROMIUM_PORT}"

# Wait for Chromium to start
echo -n "  Waiting for CDP endpoint..."
for i in $(seq 1 10); do
    if curl -s http://127.0.0.1:${CHROMIUM_PORT}/json/version >/dev/null 2>&1; then
        echo " ready!"
        break
    fi
    sleep 1
    echo -n "."
done

# ── 4. Configure OpenClaw ──────────────────────────────────
echo "[4/4] Adding Chromium profile to OpenClaw config..."
OPENCLAW_CONFIG="${OPENCLAW_HOME}/openclaw.json"

if [ -f "${OPENCLAW_CONFIG}" ]; then
    python3 -c "
import json

with open('${OPENCLAW_CONFIG}') as f:
    cfg = json.load(f)

# Add browser config section if missing
cfg.setdefault('browser', {})
cfg['browser']['enabled'] = True
cfg['browser'].setdefault('profiles', {})

# Add chromium profile (keep lightpanda as default if present)
cfg['browser']['profiles']['chromium'] = {
    'cdpUrl': 'ws://127.0.0.1:${CHROMIUM_PORT}',
    'label': 'Chromium (Cloudflare-capable)',
    'color': '#4285F4'
}

# If no default profile set, use chromium
if not cfg['browser'].get('defaultProfile'):
    cfg['browser']['defaultProfile'] = 'chromium'

with open('${OPENCLAW_CONFIG}', 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print('  Chromium profile added to openclaw.json')
" 2>/dev/null || {
    echo "  WARNING: Could not auto-configure. Add manually to ${OPENCLAW_CONFIG}:"
    cat <<'MANUAL'
  "browser": {
    "enabled": true,
    "profiles": {
      "chromium": {
        "cdpUrl": "ws://127.0.0.1:9223",
        "label": "Chromium (Cloudflare-capable)"
      }
    }
  }
MANUAL
}
else
    echo "  WARNING: ${OPENCLAW_CONFIG} not found. Run 'openclaw setup' first."
fi

# Restart OpenClaw gateway
echo ""
echo "Restarting OpenClaw gateway..."
if sudo -u "${APP_USER}" openclaw gateway restart 2>/dev/null; then
    echo "  Gateway restarted via CLI"
elif systemctl restart openclaw-watchdog 2>/dev/null; then
    echo "  Gateway restarted via systemd"
else
    echo "  WARNING: Could not auto-restart. Run manually:"
    echo "    sudo -u ${APP_USER} openclaw gateway restart"
fi

# ── Verify ─────────────────────────────────────────────────
echo ""
echo "=== Verification ==="

echo -n "Chromium service: "
systemctl is-active chromium-openclaw 2>/dev/null || echo "not running"

echo -n "CDP endpoint: "
curl -s http://127.0.0.1:${CHROMIUM_PORT}/json/version 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('Browser', 'unknown'))
" 2>/dev/null || echo "not responding"

echo -n "Lightpanda: "
systemctl is-active lightpanda 2>/dev/null || echo "not running"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Browser profiles:"
echo "  Lightpanda (port 9222) — fast, lightweight, primary"
echo "  Chromium   (port 9223) — Cloudflare-capable, fallback"
echo ""
echo "Commands:"
echo "  Status:  systemctl status chromium-openclaw"
echo "  Logs:    journalctl -u chromium-openclaw -f"
echo "  Restart: systemctl restart chromium-openclaw"
echo ""
echo "To switch default browser in OpenClaw:"
echo "  openclaw configure  →  Browser  →  Select profile"
echo ""
echo "Test in Telegram:"
echo '  "Открой https://taxes.gov.il и скажи что видишь"'
