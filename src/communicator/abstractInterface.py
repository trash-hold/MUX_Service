from abc import ABC, abstractmethod
from src.communicator.errors import ArduinoError

class CommunicationInterface(ABC):
    """
    An abstract base class that defines the contract for all communication handlers.
    The OPC UA server will interact with this interface, not the concrete implementation.
    """
    
    @abstractmethod
    def start(self) -> bool:
        """Initializes the connection to the device. Returns True on success."""
        pass

    @abstractmethod
    def stop(self):
        """Closes the connection and cleans up resources."""
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Returns True if the connection is active, False otherwise."""
        pass

    @abstractmethod
    def set_channel(self, address: int, channel: int) -> ArduinoError:
        """Commands the device to set a specific channel on a MUX."""
        pass

    @abstractmethod
    def reset_mux(self, address: int) -> ArduinoError:
        """Commands the device to reset a MUX board."""
        pass

    @abstractmethod
    def scan_i2c_bus(self) -> list[int] | None:
        """Commands the device to scan the I2C bus and return found addresses."""
        pass

    @abstractmethod
    def test_connection(self) -> str | None:
        """Sends a simple test command to check the link."""
        pass