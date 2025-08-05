import serial
import serial.tools.list_ports
import threading
import queue
import time
import logging
from enum import Enum

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ArduinoError(Enum):
    """For reference look at the firmware code"""
    SUCCESS = 0     # If the transmission is successful
    COM_ERROR = 1   # If the I2C transmission failed
    ADDR_ERROR = 2  # If given channel or I2C address is out of bounds
    UNKNOWN = -1

    @classmethod
    def from_int(cls, value: int):
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN

class SerialCommunicator:
    """
    A class to handle serial communication with the Arduino device
    Non-blocking with a separate reader thread.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Initializes the communicator.
        Args:
            port (str): The COM port to connect to (e.g., 'COM3' or '/dev/ttyUSB0').
            baudrate (int): The baudrate for the serial connection.
            timeout (float): The read timeout for the serial port.
        """
        self.ser = None
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_running = False

        self.response_queue = queue.Queue()
        self._reader_thread = None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        """
        Opens the serial port and starts the reader thread.
        Returns:
            bool: True if connection was successful, False otherwise.
        """
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            logging.info(f"Successfully opened serial port {self.port}")
        except serial.SerialException as e:
            logging.error(f"Failed to open serial port {self.port}: {e}")
            return False

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._read_from_port)
        self._reader_thread.daemon = True
        self.is_running = True
        self._reader_thread.start()
        logging.info("Reader thread started.")
        return True

    def stop(self):
        """
        Stops the reader thread and closes the serial port.
        """
        if not self.is_running:
            return

        logging.info("Stopping reader thread and closing serial port.")
        self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2) # Wait for thread to finish
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Serial port closed.")
        self.is_running = False

    def _read_from_port(self):
        """
        (Internal) The main loop for the reader thread. Reads lines from the
        serial port and puts them in the response queue.
        """
        while not self._stop_event.is_set():
            try:
                if self.ser and self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8').strip()
                    if line:
                        logging.info(f"Received: '{line}'")
                        self.response_queue.put(line)
            except serial.SerialException as e:
                logging.error(f"Serial error: {e}. Reader thread stopping.")
                break
            except Exception as e:
                logging.warning(f"An unexpected error occurred in reader thread: {e}")
            time.sleep(0.01) # Prevent high CPU usage

    def _send_command(self, command: str, timeout: float = 2.0) -> str | None:
        """
        (Internal) Sends a command to the Arduino and waits for a single-line response.
        """
        if not self.ser or not self.ser.is_open:
            logging.error("Cannot send command. Serial port is not open.")
            return None
        
        # Clear the queue of any old responses before sending a new command
        while not self.response_queue.empty():
            self.response_queue.get_nowait()

        logging.info(f"Sending: '{command}'")
        self.ser.write(f"{command}\n".encode('utf-8'))
        
        try:
            # Wait for a response to appear in the queue
            response = self.response_queue.get(timeout=timeout)
            return response
        except queue.Empty:
            logging.warning(f"No response received for command '{command}' within {timeout}s.")
            return None

    # --- Public API Methods ---

    def set_channel(self, address: int, channel: int) -> ArduinoError:
        """
        Sends the SET command to the Arduino.
        Args:
            address (int): The I2C address of the MUX board (e.g., 0x20).
            channel (int): The channel to activate (1-8).
        Returns:
            ArduinoError: The status code returned by the Arduino.
        """
        command = f"SET {address} {channel}"
        response = self._send_command(command)
        if response and response.isdigit():
            return ArduinoError.from_int(int(response))
        return ArduinoError.UNKNOWN

    def reset_mux(self, address: int) -> ArduinoError:
        """
        Sends the RESET command to the Arduino.
        Args:
            address (int): The I2C address of the MUX board (e.g., 0x20).
        Returns:
            ArduinoError: The status code returned by the Arduino.
        """
        command = f"RST {address}"
        response = self._send_command(command)
        if response and response.isdigit():
            return ArduinoError.from_int(int(response))
        return ArduinoError.UNKNOWN

    def scan_i2c_bus(self) -> list[int] | None:
        """
        Sends the SCAN command and parses the response to get a list of I2C addresses.

        Returns:
            list[int] | None: A list of found I2C addresses, or None on error.
        """
        command = "SCN"
        response = self._send_command(command, timeout=10.0)

        if response is None:
            return None
        
        # The expected response is a single line of space-separated numbers (e.g., "32 33 34")
        try:
            # Return an empty list if the response string is empty or just whitespace
            if not response.strip():
                return []
            # Split the string by spaces and convert each part to an integer
            addresses = [int(addr) for addr in response.split()]
            return addresses
        except ValueError:
            logging.error(f"Failed to parse scan response: '{response}' contains non-numeric values.")
            return None

    def test_connection(self) -> str | None:
        """Sends the TEST command to check the connection."""
        return self._send_command("TST")

    @staticmethod
    def list_available_ports():
        """A helper function to list all available serial ports."""
        ports = serial.tools.list_ports.comports()
        if not ports:
            print("No COM ports found.")
            return []
        
        print("Available COM ports:")
        port_list = []
        for port, desc, hwid in sorted(ports):
            print(f"- {port}: {desc} [{hwid}]")
            port_list.append(port)
        return port_list