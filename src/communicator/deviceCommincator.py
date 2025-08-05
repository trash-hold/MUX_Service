import logging
from threading import Lock
from src.communicator.abstractInterface import CommunicationInterface
from src.communicator.serial_communicator import ArduinoError

class MuxDevice:
    """A simple data class to hold the state of a single MUX."""
    def __init__(self, address: int):
        self.address = address
        self.active_channel = 0
        self.last_status = "IDLE"


class DeviceController:
    """
    The core business logic engine. It is agnostic to the communication protocol.
    """
    def __init__(self, communicator: CommunicationInterface):
        self.comm = communicator
        self.devices = {}  # Key: address (int), Value: MuxDevice
        self._lock = Lock()
        logging.info(f"DeviceController initialized with communicator: {type(communicator).__name__}")

    def connect(self) -> bool:
        """Starts the communicator."""
        return self.comm.start()

    def disconnect(self):
        """Stops the communicator."""
        self.comm.stop()

    def scan_for_devices(self) -> list[int]:
        """Scans for hardware, updates internal state, and returns found addresses."""
        with self._lock:
            found_addrs = self.comm.scan_i2c_bus() or []
            found_set = set(found_addrs)
            current_set = set(self.devices.keys())

            for addr in current_set - found_set:
                del self.devices[addr]
            for addr in found_set - current_set:
                self.devices[addr] = MuxDevice(addr)
            
            return list(self.devices.keys())

    def set_channel(self, address: int, channel: int) -> bool:
        """Sets the active channel for a specific MUX."""
        if address not in self.devices:
            return False
        with self._lock:
            status = self.comm.set_channel(address, channel)
            self.devices[address].last_status = status.name
            if status == ArduinoError.SUCCESS:
                self.devices[address].active_channel = channel
                return True
            return False

    def reset_mux(self, address: int) -> bool:
        """Resets a specific MUX."""
        if address not in self.devices:
            return False
            
        with self._lock:
            status = self.comm.reset_mux(address)
            self.devices[address].last_status = status.name
            if status == ArduinoError.SUCCESS:
                self.devices[address].active_channel = 0
                return True
            return False

    def get_device_states(self) -> dict[int, MuxDevice]:
        """Returns a copy of the current device states."""
        with self._lock:
            return self.devices.copy()