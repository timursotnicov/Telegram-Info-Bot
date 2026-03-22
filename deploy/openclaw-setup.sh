#!/bin/bash
# OpenClaw — one-command setup script for Hetzner CX33 (Ubuntu 24.04)
# Usage: curl -sSL <raw-url> | bash  OR  bash openclaw-setup.sh
#
# Prerequisites:
#   - Fresh Ubuntu 24.04 server (Hetzner CX33: 4 vCPU, 8GB RAM, 80GB SSD)
#   - Root SSH access
#   - OpenRouter API key ready

set -euo pipefail

APP_USER="openclaw"
OPENCLAW_DIR="/home/${APP_USER}/openclaw"
OPENCLAW_PORT=18789

echo "=== OpenClaw Server Setup ==="
echo "Target: Hetzner CX33 (4 vCPU, 8GB RAM)"
echo ""

# ── 1. System update ──────────────────────────────────────
echo "[1/6] Updating system packages..."
apt update -qq && apt upgrade -y -qq

# ── 2. Create non-root user ──────────────────────────────
echo "[2/6] Creating user '${APP_USER}'..."
if id "${APP_USER}" &>/dev/null; then
    echo "  User '${APP_USER}' already exists, skipping."
else
    adduser --disabled-password --gecos "" "${APP_USER}"
    usermod -aG sudo "${APP_USER}"
    # Copy root SSH keys to new user
    mkdir -p "/home/${APP_USER}/.ssh"
    cp /root/.ssh/authorized_keys "/home/${APP_USER}/.ssh/" 2>/dev/null || true
    chown -R "${APP_USER}:${APP_USER}" "/home/${APP_USER}/.ssh"
    chmod 700 "/home/${APP_USER}/.ssh"
    chmod 600 "/home/${APP_USER}/.ssh/authorized_keys" 2>/dev/null || true
    # Allow sudo without password for setup
    echo "${APP_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${APP_USER}"
fi

# ── 3. Firewall ──────────────────────────────────────────
echo "[3/6] Configuring firewall (UFW)..."
apt install -y -qq ufw
ufw allow OpenSSH
ufw allow ${OPENCLAW_PORT}/tcp comment "OpenClaw Control UI"
ufw --force enable

# Harden SSH: disable root password login
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# ── 4. Install Docker ────────────────────────────────────
echo "[4/6] Installing Docker..."
if command -v docker &>/dev/null; then
    echo "  Docker already installed, skipping."
else
    curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker "${APP_USER}"

# ── 5. Clone & setup OpenClaw ────────────────────────────
echo "[5/6] Installing OpenClaw..."
sudo -u "${APP_USER}" bash -c "
    cd /home/${APP_USER}
    if [ -d openclaw ]; then
        cd openclaw && git pull origin main
    else
        git clone https://github.com/openclaw/openclaw.git
        cd openclaw
    fi
"

echo ""
echo "========================================="
echo "  OpenClaw cloned to: ${OPENCLAW_DIR}"
echo ""
echo "  Next steps (run as '${APP_USER}' user):"
echo ""
echo "  1. SSH as openclaw user:"
echo "     ssh ${APP_USER}@$(hostname -I | awk '{print $1}')"
echo ""
echo "  2. Run the OpenClaw setup:"
echo "     cd ~/openclaw"
echo "     ./scripts/docker/setup.sh"
echo ""
echo "  3. During onboarding, enter:"
echo "     - Provider: OpenRouter"
echo "     - API Key: your OPENROUTER_API_KEY"
echo "     - Model: gemma-3-27b-it:free"
echo ""
echo "  4. Open Control UI:"
echo "     http://$(hostname -I | awk '{print $1}'):${OPENCLAW_PORT}/"
echo ""
echo "  5. (Optional) Enable sandbox mode:"
echo "     OPENCLAW_SANDBOX=1 ./scripts/docker/setup.sh"
echo "========================================="

# ── 6. Setup auto-restart via systemd ────────────────────
echo "[6/6] Creating systemd watchdog..."
cat > /etc/systemd/system/openclaw-watchdog.service <<UNIT
[Unit]
Description=OpenClaw Docker Compose Watchdog
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=${APP_USER}
WorkingDirectory=${OPENCLAW_DIR}
ExecStart=/usr/bin/docker compose up -d
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable openclaw-watchdog

echo ""
echo "=== Setup complete! ==="
echo "Server is ready for OpenClaw. Follow the steps above."
