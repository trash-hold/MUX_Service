from enum import Enum

class ArduinoError(Enum):
    """Mirrors the ErrorCodes enum in the Arduino code. Placed here for shared use."""
    SUCCESS = 0
    COM_ERROR = 1
    ADDR_ERROR = 2
    UNKNOWN = -1

    @classmethod
    def from_int(cls, value: int):
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN