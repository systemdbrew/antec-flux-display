# Antec Flux Pro Display Service for Linux

A lightweight Python service that sends CPU and GPU temperatures to the Antec Flux Pro case's front panel display on Linux. No Windows or Antec iUnity software required.

Tested on CachyOS (Arch-based) with AMD Ryzen 9900X + AMD 7900 XTX. Should work on any Linux distro with Python 3 and an AMD CPU/GPU, with minor tweaks for Intel/NVIDIA (see [Configuration](#configuration)).

## How It Works

The Antec Flux Pro has a temperature display on the side panel that communicates over an internal USB 2.0 header. The official iUnity software is Windows-only. This service replaces it by reading temperatures from the kernel's hwmon sysfs interface and writing a 12-byte packet to the display's USB interrupt endpoint every second.

### USB Protocol

The display uses vendor ID `2022` and product ID `0522`. It exposes a single interrupt OUT endpoint (`0x03`) and accepts a 12-byte packet:

| Byte | Value | Description |
|------|-------|-------------|
| 0 | `0x55` | Header |
| 1 | `0xAA` | Header |
| 2 | `0x01` | Command |
| 3 | `0x01` | Command |
| 4 | `0x06` | Command |
| 5 | `0x00-0x09` | CPU temp tens digit |
| 6 | `0x00-0x09` | CPU temp ones digit |
| 7 | `0x00-0x09` | CPU temp tenths digit |
| 8 | `0x00-0x09` | GPU temp tens digit |
| 9 | `0x00-0x09` | GPU temp ones digit |
| 10 | `0x00-0x09` | GPU temp tenths digit |
| 11 | checksum | Sum of bytes 0-10, mod 256 |

Sending `0xEE` for all three digit bytes of a temperature displays `--.-` on that line.

Protocol details were reverse-engineered from the Antec iUnity Windows binary. Credit to [Nish Tahir's blog post](https://nishtahir.com/building-an-ubuntu-service-for-my-antec-flux-display/) for the original reverse engineering work.

## Requirements

- Python 3.10+
- `python-pyusb` (Arch/CachyOS) or `pyusb` (pip)
- Internal USB 2.0 header connected to the Flux Pro display cable

## Installation

```bash
git clone https://github.com/systemdbrew/antec-flux-display.git
cd antec-flux-display
sudo bash install.sh
```

The install script will:
1. Install `python-pyusb` if not present
2. Copy the service script to `/opt/antec-flux-display/`
3. Install a udev rule for device permissions
4. Install and enable a systemd service

## Uninstallation

```bash
sudo bash uninstall.sh
```

## Usage

The service starts automatically on boot. Manage it with:

```bash
# Check status
systemctl status antec-flux-display

# View live logs
journalctl -u antec-flux-display -f

# Restart after config changes
sudo systemctl restart antec-flux-display

# Stop
sudo systemctl stop antec-flux-display
```

The display button on top of the case toggles the screen on/off. The service continues running in the background regardless.

## Configuration

Edit `/opt/antec-flux-display/antec-flux-display.py` to change sensor sources.

### AMD CPU + AMD GPU (default)
No changes needed. Reads `k10temp` for CPU and `amdgpu` for GPU.

### AMD CPU + NVIDIA GPU
Change the GPU hwmon lookup:
```python
gpu_hwmon = find_hwmon_path("nvidia")
```
You may also need to check which `temp*_input` file corresponds to GPU temp.

### Intel CPU
Change the CPU hwmon lookup:
```python
cpu_hwmon = find_hwmon_path("coretemp")
```

### Temperature source
By default, CPU reads `temp1_input` (Tctl on AMD) and GPU reads `temp1_input` (edge on AMD). To change, modify the `cpu_temp_file` or `gpu_temp_file` variables. Common options:

**k10temp (AMD CPU):**
- `temp1_input` — Tctl (default, includes +15°C offset on some CPUs)
- `temp3_input` — Tccd0 (actual die temp, if available)

**amdgpu (AMD GPU):**
- `temp1_input` — Edge (default)
- `temp2_input` — Junction (hotspot)
- `temp3_input` — Memory

## Troubleshooting

### Display shows --.-
- Check that the service is running: `systemctl status antec-flux-display`
- Check logs: `journalctl -u antec-flux-display -f`
- Verify sensors exist: `cat /sys/class/hwmon/hwmon*/name`

### Service fails to start
- Verify the display is connected: `lsusb | grep 2022`
- Try running manually: `sudo python3 /opt/antec-flux-display/antec-flux-display.py`
- Check that pyusb is installed: `python3 -c "import usb.core; print('ok')"`

### Slow boot with display connected
Some motherboard USB headers cause enumeration delays with this device. Try a different internal USB 2.0 header on your motherboard. If that doesn't help, add a kernel parameter: `usbcore.quirks=2022:0522:gk`

### Device not found but lsusb shows it
The device only has an interrupt OUT endpoint and doesn't enumerate as standard HID on Linux. This service uses pyusb/libusb to communicate directly. Make sure `python-pyusb` is installed, not `python-hidapi`.

## Hardware Compatibility

Confirmed working:
- Antec Flux Pro (2024)

Likely compatible (same display module):
- Other Antec cases using the iUnity display

## License

MIT
