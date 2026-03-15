#!/bin/bash
# SaveBot — one-command deploy script for Oracle Cloud (Ubuntu/ARM)
# Usage: bash setup.sh

set -e

APP_DIR="/opt/savebot"
REPO_URL="https://github.com/timursotnicov/Telegram-Info-Bot.git"
SERVICE_NAME="savebot"

echo "=== SaveBot Deploy ==="

# 1. Install system dependencies
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git sqlite3

# 2. Clone or update repo
echo "[2/6] Setting up app directory..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    sudo mkdir -p "$APP_DIR"
    sudo chown "$USER:$USER" "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Python virtual environment
echo "[3/6] Setting up Python venv..."
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 4. Create .env if not exists
if [ ! -f "$APP_DIR/.env" ]; then
    echo "[4/6] Creating .env file..."
    cp .env.example .env
    echo ""
    echo "========================================="
    echo "  EDIT .env FILE WITH YOUR TOKENS:"
    echo "  nano $APP_DIR/.env"
    echo "========================================="
    echo ""
    read -p "Press Enter after editing .env, or Ctrl+C to do it later..."
else
    echo "[4/6] .env already exists, skipping..."
fi

# 5. Install systemd service
echo "[5/6] Setting up systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<UNIT
[Unit]
Description=SaveBot Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python -m savebot.bot
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

# 6. Setup daily SQLite backup cron
echo "[6/6] Setting up daily backup..."
BACKUP_DIR="$APP_DIR/backups"
mkdir -p "$BACKUP_DIR"
(crontab -l 2>/dev/null | grep -v "savebot_backup"; echo "0 3 * * * sqlite3 $APP_DIR/savebot.db \".backup '$BACKUP_DIR/savebot_\$(date +\%Y\%m\%d).db'\" && find $BACKUP_DIR -name '*.db' -mtime +7 -delete") | crontab -

echo ""
echo "=== Done! ==="
echo "Status:  sudo systemctl status $SERVICE_NAME"
echo "Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "Stop:    sudo systemctl stop $SERVICE_NAME"
echo "Restart: sudo systemctl restart $SERVICE_NAME"
