#!/usr/bin/env python3
"""
Antec Flux Pro Display Service
Sends CPU and GPU temperatures to the case front panel display.

Protocol reverse-engineered from Antec iUnity Windows software.
Reference: https://nishtahir.com/building-an-ubuntu-service-for-my-antec-flux-display/

Uses pyusb (libusb) to write directly to the interrupt OUT endpoint,
since the device doesn't enumerate as a standard HID device on Linux.

Hardware: AMD Ryzen 9900X (k10temp) + AMD 7900 XTX (amdgpu)
"""

import errno
import glob
import logging
import time
import sys
import signal

import usb.core
import usb.util

VENDOR_ID = 0x2022
PRODUCT_ID = 0x0522
ENDPOINT_OUT = 0x03
UPDATE_INTERVAL = 1.0  # seconds
DISPLAY_ID = f"{VENDOR_ID:04x}:{PRODUCT_ID:04x}"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOG = logging.getLogger("antec-flux-display")


def find_hwmon_path(device_name: str) -> str | None:
    """Find the hwmon sysfs path for a given device."""
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(f"{hwmon}/name") as f:
                if f.read().strip() == device_name:
                    return hwmon
        except (IOError, OSError):
            continue
    return None


def read_temp(hwmon_path: str, input_file: str = "temp1_input") -> float:
    """Read temperature from hwmon sysfs (returns °C)."""
    try:
        with open(f"{hwmon_path}/{input_file}") as f:
            return int(f.read().strip()) / 1000.0
    except (IOError, OSError, ValueError):
        return 0.0


def encode_temperature(temp: float | None) -> list[int]:
    """Encode a temperature as 3 bytes: [tens, ones, tenths].

    If temp is unavailable, returns [0xEE, 0xEE, 0xEE] (display shows --.-).
    """
    if temp is None or temp <= 0.0:
        return [0xEE, 0xEE, 0xEE]

    # Clamp to 99.9
    temp = min(temp, 99.9)
    formatted = f"{temp:04.1f}"  # e.g. "52.3" -> "52.3", "8.1" -> "08.1"

    tens = int(formatted[0])
    ones = int(formatted[1])
    tenths = int(formatted[3])

    return [tens, ones, tenths]


def build_packet(cpu_temp: float, gpu_temp: float) -> bytes:
    """Build the 12-byte USB packet for the display.

    Packet format:
      [0x55, 0xAA, 0x01, 0x01, 0x06,
       cpu_tens, cpu_ones, cpu_tenths,
       gpu_tens, gpu_ones, gpu_tenths,
       checksum]
    """
    payload = [0x55, 0xAA, 0x01, 0x01, 0x06]
    payload.extend(encode_temperature(cpu_temp))
    payload.extend(encode_temperature(gpu_temp))

    checksum = sum(payload) % 256
    payload.append(checksum)

    return bytes(payload)


def find_display_endpoint(dev):
    """Find the expected interrupt OUT endpoint on interface 0."""
    cfg = dev.get_active_configuration()
    intf = usb.util.find_descriptor(cfg, bInterfaceNumber=0)
    if intf is None:
        raise usb.core.USBError("interface 0 not found")

    endpoint = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: (
            e.bEndpointAddress == ENDPOINT_OUT
            and usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR
        ),
    )
    if endpoint is None:
        raise usb.core.USBError(f"interrupt OUT endpoint 0x{ENDPOINT_OUT:02x} not found")
    return endpoint.bEndpointAddress


def close_display(dev) -> None:
    """Release the USB interface when it was claimed."""
    if dev is None:
        return
    try:
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)
    except usb.core.USBError:
        pass


def open_display():
    """Open the Antec Flux Pro USB device and return the device and endpoint."""
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        return None

    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except NotImplementedError:
        pass

    try:
        dev.set_configuration()
    except usb.core.USBError as e:
        if e.errno != errno.EBUSY:
            raise

    try:
        usb.util.claim_interface(dev, 0)
        endpoint = find_display_endpoint(dev)
    except usb.core.USBError:
        close_display(dev)
        raise
    return dev, endpoint


def main() -> int:
    cpu_hwmon = find_hwmon_path("k10temp")
    if not cpu_hwmon:
        LOG.error("k10temp hwmon not found. Is the k10temp module loaded?")
        return 1

    gpu_hwmon = find_hwmon_path("amdgpu")
    if not gpu_hwmon:
        LOG.warning("amdgpu hwmon not found. GPU temp will show --.-")

    LOG.info("CPU sensor: %s", cpu_hwmon)
    LOG.info("GPU sensor: %s", gpu_hwmon or "not found")

    # k10temp: temp1_input = Tctl
    cpu_temp_file = "temp1_input"
    # amdgpu: temp1_input = edge
    gpu_temp_file = "temp1_input"

    try:
        display = open_display()
    except usb.core.USBError as e:
        LOG.error("Could not open display device %s: %s", DISPLAY_ID, e)
        LOG.error("Check udev permissions and service group membership.")
        return 1

    if display is None:
        LOG.error("Could not find display device %s", DISPLAY_ID)
        LOG.error("Is the display USB header connected?")
        return 1
    dev, endpoint = display

    LOG.info("Display connected: %s", DISPLAY_ID)

    running = True

    def shutdown(signum, frame):
        nonlocal running
        LOG.info("Received signal %s, shutting down...", signum)
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    LOG.info("Sending temps every %.1fs.", UPDATE_INTERVAL)
    try:
        while running:
            cpu_temp = read_temp(cpu_hwmon, cpu_temp_file)
            gpu_temp = read_temp(gpu_hwmon, gpu_temp_file) if gpu_hwmon else 0.0

            packet = build_packet(cpu_temp, gpu_temp)

            try:
                dev.write(endpoint, packet)
            except usb.core.USBError as e:
                LOG.error("USB write error: %s", e)
                # Try to reconnect
                close_display(dev)
                try:
                    display = open_display()
                except usb.core.USBError as reconnect_error:
                    LOG.error("Could not reopen display: %s", reconnect_error)
                    return 1
                if display is None:
                    LOG.error("Lost connection to display")
                    return 1
                dev, endpoint = display

            time.sleep(UPDATE_INTERVAL)
    except usb.core.USBError as e:
        LOG.error("%s", e)
        return 1
    finally:
        close_display(dev)
        LOG.info("Display service stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
