#!/bin/bash

# service_install.sh

# Exit on any error
set -e

# Get the current username
CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" = "root" ]; then
    echo "Please run this script as a non-root user with sudo privileges"
    exit 1
fi

# Get the absolute path of the directory where the script is located
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="systemd_dashboard"

# Create systemd service file
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Flask Apps Portal
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${INSTALL_DIR}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="FLASK_APP=app.py"
Environment="FLASK_ENV=production"
ExecStart=${INSTALL_DIR}/.venv/bin/python3 ${INSTALL_DIR}/app.py
Restart=always
RestartSec=3
Nice=10
CPUQuota=50%
MemoryLimit=256M

# Hardening
ProtectSystem=full
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Set correct permissions for the service file
sudo chmod 644 /etc/systemd/system/${SERVICE_NAME}.service

# Create virtual environment and install requirements if they don't exist
if [ ! -d "${INSTALL_DIR}/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "${INSTALL_DIR}/.venv"
    
    echo "Installing required packages..."
    "${INSTALL_DIR}/.venv/bin/pip" install flask
    
    # If you have a requirements.txt file, uncomment the following line:
    # "${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
fi

# Verify that app.py exists in the installation directory
if [ ! -f "${INSTALL_DIR}/app.py" ]; then
    echo "Error: app.py not found in ${INSTALL_DIR}"
    exit 1
fi

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling ${SERVICE_NAME} service..."
sudo systemctl enable ${SERVICE_NAME}.service

echo "Starting ${SERVICE_NAME} service..."
sudo systemctl start ${SERVICE_NAME}.service

echo "Checking service status..."
sudo systemctl status ${SERVICE_NAME}.service

echo "Installation completed successfully!"
echo "To view logs, run: journalctl -u ${SERVICE_NAME}.service -f"
echo "To check status, run: systemctl status ${SERVICE_NAME}.service"