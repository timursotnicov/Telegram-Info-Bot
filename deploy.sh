#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/savebot}"
REPO_URL="${REPO_URL:-https://github.com/timursotnicov/Telegram-Info-Bot.git}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
SERVICE_NAME="${SERVICE_NAME:-savebot}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
  RUN_USER="${SUDO_USER:-ubuntu}"
else
  SUDO="sudo"
  RUN_USER="$(id -un)"
fi

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

compose() {
  if $SUDO docker compose version >/dev/null 2>&1; then
    $SUDO docker compose -f "$COMPOSE_FILE" "$@"
  elif need_cmd docker-compose; then
    $SUDO docker-compose -f "$COMPOSE_FILE" "$@"
  else
    echo "Docker Compose is not installed." >&2
    exit 1
  fi
}

install_packages() {
  log "Installing system packages"
  $SUDO apt-get update
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl git ufw fail2ban docker.io sqlite3
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin \
    || $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose

  $SUDO systemctl enable --now docker
  $SUDO usermod -aG docker "$RUN_USER" || true
}

hardening() {
  log "Applying SSH, firewall, and fail2ban hardening"

  $SUDO mkdir -p /etc/ssh/sshd_config.d
  $SUDO tee /etc/ssh/sshd_config.d/99-savebot-hardening.conf >/dev/null <<'SSHCONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
X11Forwarding no
SSHCONF

  $SUDO mkdir -p /etc/fail2ban/jail.d
  $SUDO tee /etc/fail2ban/jail.d/sshd.local >/dev/null <<'JAIL'
[sshd]
enabled = true
mode = normal
port = ssh
maxretry = 5
findtime = 10m
bantime = 1h
JAIL

  $SUDO systemctl enable --now fail2ban
  $SUDO systemctl restart fail2ban

  $SUDO ufw default deny incoming
  $SUDO ufw default allow outgoing
  $SUDO ufw allow OpenSSH
  $SUDO ufw --force enable

  if systemctl list-unit-files | grep -Eq '^ssh\.service'; then
    $SUDO systemctl reload ssh || $SUDO systemctl restart ssh
  elif systemctl list-unit-files | grep -Eq '^sshd\.service'; then
    $SUDO systemctl reload sshd || $SUDO systemctl restart sshd
  fi
}

checkout_repo() {
  log "Checking out $REPO_URL ($BRANCH)"
  if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git fetch origin "$BRANCH"
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git switch "$BRANCH"
    else
      git switch --track -c "$BRANCH" "origin/$BRANCH"
    fi
    git pull --ff-only origin "$BRANCH"
  else
    $SUDO mkdir -p "$APP_DIR"
    $SUDO chown "$RUN_USER:$RUN_USER" "$APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
  fi
}

install_entrypoint() {
  log "Installing deploy.sh entrypoint"
  local src="$APP_DIR/deploy.sh"
  if [ ! -f "$src" ]; then
    src="$(readlink -f "$0")"
  fi
  $SUDO cp "$src" /root/deploy.sh
  $SUDO chmod 700 /root/deploy.sh
  $SUDO ln -sf /root/deploy.sh /usr/local/bin/deploy.sh
}

prepare_env() {
  log "Preparing production environment"
  mkdir -p "$APP_DIR/data" "$APP_DIR/backups"

  if [ ! -f "$APP_DIR/.env.prod" ]; then
    if [ -f "$APP_DIR/.env.prod.example" ]; then
      cp "$APP_DIR/.env.prod.example" "$APP_DIR/.env.prod"
    fi
    chmod 600 "$APP_DIR/.env.prod" || true
    echo "Created $APP_DIR/.env.prod. Fill BOT_TOKEN and OPENROUTER_API_KEY, then rerun deploy.sh." >&2
    exit 1
  fi

  chmod 600 "$APP_DIR/.env.prod"
}

backup_db() {
  local db="$APP_DIR/data/savebot.db"
  if [ -f "$db" ]; then
    log "Backing up SQLite database"
    sqlite3 "$db" ".backup '$APP_DIR/backups/savebot_$(date +%Y%m%d_%H%M%S).db'"
    find "$APP_DIR/backups" -name 'savebot_*.db' -mtime +"$BACKUP_KEEP_DAYS" -delete
  fi
}

deploy_app() {
  log "Building and starting Docker service"
  cd "$APP_DIR"
  compose build
  compose up -d --remove-orphans
}

show_status() {
  log "Deployment status"
  cd "$APP_DIR"
  compose ps
  echo
  compose logs --tail=40 "$SERVICE_NAME"
}

main() {
  install_packages
  hardening
  checkout_repo
  install_entrypoint
  prepare_env
  backup_db
  deploy_app
  show_status

  log "Done. Re-run deploy.sh any time to pull latest git and restart production."
}

main "$@"
