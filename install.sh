#!/bin/bash
# Install script for Antec Flux Pro Display Service
# Run with: sudo bash install.sh

set -euo pipefail

echo "=== Antec Flux Pro Display Service Installer ==="

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo bash install.sh)"
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SERVICE_USER="antec-flux-display"
SERVICE_GROUP="antec-flux-display"
INSTALL_DIR="/opt/antec-flux-display"
NOLOGIN_SHELL="$(command -v nologin || printf /usr/sbin/nologin)"

install_pyusb() {
    if python3 -c "import usb.core" >/dev/null 2>&1; then
        return
    fi

    if command -v pacman >/dev/null 2>&1; then
        pacman -S --noconfirm --needed python-pyusb
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get install -y python3-usb
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y python3-pyusb
    elif command -v zypper >/dev/null 2>&1; then
        zypper --non-interactive install python3-pyusb
    else
        echo "ERROR: pyusb is not installed and no supported package manager was found." >&2
        echo "Install pyusb from your distribution packages, then rerun this script." >&2
        exit 1
    fi
}

echo "[1/7] Installing pyusb dependency..."
install_pyusb

echo "[2/7] Creating service user and group..."
if ! getent group "$SERVICE_GROUP" >/dev/null; then
    groupadd --system "$SERVICE_GROUP"
fi

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd \
        --system \
        --gid "$SERVICE_GROUP" \
        --home-dir /nonexistent \
        --shell "$NOLOGIN_SHELL" \
        --no-create-home \
        "$SERVICE_USER"
fi

echo "[3/7] Installing service script..."
install -d -o root -g root -m 0755 "$INSTALL_DIR"
install -o root -g root -m 0755 "$SCRIPT_DIR/antec-flux-display.py" "$INSTALL_DIR/antec-flux-display.py"

echo "[4/7] Installing udev rule..."
install -o root -g root -m 0644 "$SCRIPT_DIR/99-antec-flux-display.rules" /etc/udev/rules.d/99-antec-flux-display.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=2022 --attr-match=idProduct=0522 || true
udevadm settle

echo "[5/7] Installing systemd service..."
install -o root -g root -m 0644 "$SCRIPT_DIR/antec-flux-display.service" /etc/systemd/system/antec-flux-display.service
systemctl daemon-reload

echo "[6/7] Enabling service..."
systemctl enable antec-flux-display.service

echo "[7/7] Starting service..."
systemctl restart antec-flux-display.service

echo ""
echo "=== Installation complete ==="
echo ""
echo "Check status:  systemctl status antec-flux-display"
echo "View logs:     journalctl -u antec-flux-display -f"
echo "Stop service:  sudo systemctl stop antec-flux-display"
echo "Uninstall:     sudo bash uninstall.sh"
