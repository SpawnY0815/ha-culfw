"""USB link reset for the USB device behind a serial port."""

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from usb_devices import USBDevice

SYS_CLASS_TTY = Path("/sys/class/tty")


def _load_usb_device() -> type[USBDevice]:
    """Import the usb-devices package and return its device class.

    The import reads files, so it blocks. The package loads only when a reset is due,
    so a broken installation of it costs this one recovery step and not the whole
    integration.

    Raises:
        ImportError: The usb-devices package cannot be imported.
    """
    from usb_devices import USBDevice  # noqa: PLC0415

    return USBDevice


def usb_interface_of_tty(port: str, *, sys_class_tty: Path = SYS_CLASS_TTY) -> str:
    """Return the USB interface id behind a tty path, for example `3-6.4:1.0`.

    The port may be a symlink such as `/dev/serial/by-id/...`. This reads sysfs, so it
    blocks.

    Raises:
        OSError: The tty has no sysfs entry.
    """
    tty = Path(os.path.realpath(port)).name
    return (sys_class_tty / tty / "device").readlink().name


class UsbLinkReset:
    """Watchdog hook that resets the USB link of a serial port.

    The ioctl comes from the usb-devices package, which the bluetooth integration of
    Home Assistant also uses to reset stuck adapters. A link reset runs the USB
    handshake again but does not reset the AVR of the CUL, so the FHT buffers of culfw
    survive. The kernel driver may be unbound and bound again, and then the tty can come
    back under another name, so always open the port by its /dev/serial/by-id path. The
    reset reaches the stick only when the whole USB device is passed through, for
    example to a virtual machine. Never use it for a tty that is bound into a container
    by path.
    """

    def __init__(self, port: str, *, sys_class_tty: Path = SYS_CLASS_TTY) -> None:
        """Initialize the hook for a serial port path."""
        self._port = port
        self._sys_class_tty = sys_class_tty

    async def __call__(self) -> str:
        """Reset the link and return a short description.

        Raises:
            ImportError: The usb-devices package cannot be imported.
            OSError: The tty has no sysfs entry, or the reset is not supported.
            ValueError: The tty is not a USB device.
        """
        usb_device = await asyncio.to_thread(_load_usb_device)
        interface = await asyncio.to_thread(
            usb_interface_of_tty, self._port, sys_class_tty=self._sys_class_tty
        )
        if not await usb_device(interface).async_reset():
            raise OSError(f"USBDEVFS_RESET is not supported here (device {interface})")
        return f"USB device {interface} reset"
