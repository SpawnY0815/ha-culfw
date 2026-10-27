"""Errors raised by the CUL transport."""


class CulError(Exception):
    """Base error of the CUL transport."""


class CulConnectionError(CulError):
    """The serial port cannot be opened, was lost or is not connected."""


class CulPortMissingError(CulConnectionError):
    """The serial port does not exist, for example because the stick is unplugged."""


class CulPortBusyError(CulConnectionError):
    """Another process has the serial port open."""


class CulPortPermissionError(CulConnectionError):
    """The process is not allowed to open the serial port."""


class CulTimeoutError(CulError):
    """The CUL did not answer a command in time."""


class CulProtocolError(CulError):
    """The CUL answered something unexpected."""


class CulCommandBlockedError(CulError):
    """A command was rejected because it is blocked or not on the allow list."""


class FhtValueError(ValueError):
    """A value cannot be sent to an FHT80b, for example a temperature out of range."""
