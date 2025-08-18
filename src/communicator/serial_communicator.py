import serial
import serial.tools.list_ports
import threading
import queue
import time
import logging
from src.communicator.errors import ArduinoError

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SerialCommunicator:
    """
    A robust, thread-safe class to handle serial communication with a device.
    It automatically handles disconnects and provides a clear connection status.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.ser = None
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        self.is_connected = False

        self.response_queue = queue.Queue()
        self._reader_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> bool:
        """
        Opens the serial port and starts the reader thread.
        Returns:
            bool: True if connection was successful, False otherwise.
        """
        with self._lock:
            if self.is_connected:
                return True
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                logging.info(f"Successfully opened serial port {self.port}")
            except serial.SerialException as e:
                logging.error(f"Failed to open serial port {self.port}: {e}")
                self.ser = None
                return False

            self._stop_event.clear()
            self._reader_thread = threading.Thread(target=self._read_from_port)
            self._reader_thread.daemon = True
            self.is_connected = True
            self._reader_thread.start()
            logging.info("Reader thread started.")
            return True

    def stop(self):
        """
        Stops the reader thread and closes the serial port in a thread-safe manner.
        """
        with self._lock:
            if not self.is_connected:
                return

            logging.info("Stopping reader thread and closing serial port.")
            self._stop_event.set()
            
            # Close the serial port immediately to cause the reader thread to exit
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except serial.SerialException as e:
                    logging.warning(f"Error closing serial port: {e}")
            
            self.is_connected = False
            self.ser = None
        
        # Join the thread outside the lock to prevent deadlocks
        if self._reader_thread and threading.current_thread() != self._reader_thread:
            self._reader_thread.join(timeout=2.0)
            if self._reader_thread.is_alive():
                logging.warning("Reader thread did not terminate in time.")
        
        logging.info("Communication stopped.")


    def _read_from_port(self):
        """
        (Internal) The main loop for the reader thread.
        """
        while not self._stop_event.is_set():
            try:
                # The check 'self.ser and self.ser.is_open' is crucial
                if self.ser and self.ser.is_open and self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8').strip()
                    if line:
                        logging.info(f"Received: '{line}'")
                        self.response_queue.put(line)
                else:
                    # Short sleep to prevent busy-waiting when there's no data
                    time.sleep(0.01)

            except (serial.SerialException, OSError) as e:
                logging.error(f"Serial error: {e}. Device disconnected.")
                self.stop() # Trigger a clean shutdown
                break # Exit the thread loop
            except Exception as e:
                logging.warning(f"An unexpected error occurred in reader thread: {e}")

    def _send_command(self, command: str, timeout: float = 2.0) -> str | None:
        """
        (Internal) Sends a command and waits for a response. Now handles disconnects.
        """
        # --- CHANGE: Check the 'is_connected' flag first ---
        if not self.is_connected:
            logging.error("Cannot send command. Not connected.")
            return None
        
        with self._lock:
            # Re-check connection status after acquiring lock
            if not self.is_connected or not self.ser:
                logging.error("Cannot send command. Connection lost.")
                return None
            
            while not self.response_queue.empty():
                self.response_queue.get_nowait()

            try:
                logging.info(f"Sending: '{command}'")
                self.ser.write(f"{command}\n".encode('utf-8'))
            except (serial.SerialException, OSError) as e:
                logging.error(f"Failed to write to serial port: {e}. Device disconnected.")
                self.stop()
                return None

        try:
            response = self.response_queue.get(timeout=timeout)
            return response
        except queue.Empty:
            logging.warning(f"No response received for command '{command}' within {timeout}s.")
            if not self.test_connection():
                 logging.error("Device is not responding after timeout. Assuming disconnection.")
                 self.stop()
            return None

    # --- Public API Methods (no major changes needed, but they are now more robust) ---

    def set_channel(self, address: int, channel: int) -> ArduinoError:
        command = f"SET {address} {channel}"
        response = self._send_command(command)
        if response and response.isdigit():
            return ArduinoError.from_int(int(response))
        return ArduinoError.UNKNOWN

    def reset_mux(self, address: int) -> ArduinoError:
        command = f"RST {address}"
        response = self._send_command(command)
        if response and response.isdigit():
            return ArduinoError.from_int(int(response))
        return ArduinoError.UNKNOWN

    def scan_i2c_bus(self) -> list[int] | None:
        command = "SCN"
        response = self._send_command(command, timeout=10.0)
        if response is None:
            return None
        try:
            if not response.strip():
                return []
            return [int(addr) for addr in response.split()]
        except ValueError:
            logging.error(f"Failed to parse scan response: '{response}'")
            return None

    def test_connection(self) -> bool:
        """Sends a test command. Returns True on success, False otherwise."""
        response = self._send_command("TST", timeout=1.0)
        return response is not None

    # Static method remains the same
    @staticmethod
    def list_available_ports():
        pass