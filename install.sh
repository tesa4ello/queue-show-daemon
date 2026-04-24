#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "❌ Run with sudo: sudo bash install.sh"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
INSTALL_DIR="/opt/asterisk-queue-proxy"
SERVICE_NAME="asterisk-queue-proxy"
SYSTEMD_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$(command -v python3 || echo "/usr/bin/python3")"

echo "🔧 Installing ${SERVICE_NAME}..."

# 1. Подготовка директории
mkdir -p "${INSTALL_DIR}"
cp -r "${SCRIPT_DIR}"/* "${INSTALL_DIR}/"

# 2. Инициализация .env
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    cp ".env.example" "${INSTALL_DIR}/.env"
    echo "📝 .env created from template. Edit before first run!"
fi

# 3. Генерация systemd-юнита с подстановкой путей
echo "⚙️ Generating systemd unit..."
cat > "${SYSTEMD_FILE}" <<EOF
[Unit]
Description=Asterisk Queue Proxy Daemon
After=network.target asterisk.service
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${PYTHON_BIN} ${INSTALL_DIR}/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

# 4. Регистрация и запуск
echo "🔄 Reloading systemd..."
systemctl daemon-reload

echo "🚀 Enabling & starting service..."
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

echo ""
echo "✅ Installation complete!"
echo "📊 Status:  systemctl status ${SERVICE_NAME}"
echo "📝 Logs:    journalctl -u ${SERVICE_NAME} -f"
echo "⚙️  Config:  nano ${INSTALL_DIR}/.env && systemctl restart ${SERVICE_NAME}"
