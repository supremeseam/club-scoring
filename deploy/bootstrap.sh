#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 24.04 arm64 EC2 instance. Run via SSM Session Manager as root:
#   sudo bash deploy/bootstrap.sh https://github.com/<club>/<repo>.git
set -euo pipefail
REPO_URL="${1:?usage: bootstrap.sh <git repo url>}"
APP_DIR=/opt/scoring

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades

# --- Docker (official repo) ---
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# --- Automatic security patches, with reboot at a quiet hour ---
cat > /etc/apt/apt.conf.d/52scoring-unattended <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
EOF
systemctl enable --now unattended-upgrades

# --- 1 GB swapfile (t4g.micro has 1 GB RAM; image builds need headroom) ---
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- App checkout and secrets file ---
[ -d "$APP_DIR/.git" ] || git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=')
  sed -i "s/^DEBUG=.*/DEBUG=0/; s/^SECRET_KEY=.*/SECRET_KEY=${SECRET}/" .env
  chmod 600 .env
  echo ">>> Edit $APP_DIR/.env: set SITE_ADDRESS, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, PUBLIC_URL, CLUB_NAME, TIME_ZONE, LITESTREAM_BUCKET."
fi
# Expired login sessions are purged nightly.
echo "17 3 * * * root docker compose -f $APP_DIR/compose.yml exec -T app python manage.py clearsessions" > /etc/cron.d/scoring-clearsessions
echo "Bootstrap done. Next: edit .env, then run deploy/deploy.sh"
