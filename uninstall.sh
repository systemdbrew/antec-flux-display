#!/bin/bash
# Uninstall script for Antec Flux Pro Display Service
# Run with: sudo bash uninstall.sh

set -euo pipefail

echo "=== Antec Flux Pro Display Service Uninstaller ==="

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo bash uninstall.sh)"
    exit 1
fi

SERVICE_USER="antec-flux-display"
SERVICE_GROUP="antec-flux-display"

echo "[1/5] Stopping service..."
systemctl stop antec-flux-display.service 2>/dev/null || true
systemctl disable antec-flux-display.service 2>/dev/null || true

echo "[2/5] Removing systemd service..."
rm -f /etc/systemd/system/antec-flux-display.service
systemctl daemon-reload

echo "[3/5] Removing udev rule..."
rm -f /etc/udev/rules.d/99-antec-flux-display.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=2022 --attr-match=idProduct=0522 || true
udevadm settle || true

echo "[4/5] Removing service files..."
rm -rf /opt/antec-flux-display

echo "[5/5] Removing service user and group..."
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    userdel "$SERVICE_USER" 2>/dev/null || true
fi

if getent group "$SERVICE_GROUP" >/dev/null; then
    groupdel "$SERVICE_GROUP" 2>/dev/null || true
fi

echo ""
echo "=== Uninstallation complete ==="
