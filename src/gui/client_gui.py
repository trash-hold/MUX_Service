import asyncio
from qasync import asyncSlot
import logging
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QSpinBox, QFrame, QTextEdit
from PySide6.QtCore import Qt, Signal, QObject

# Assuming clientLogic.py is in the same directory or a reachable path
from src.opc_ua.clientLogic import OpcUaClientLogic

# --- Logging Setup (Unchanged) ---
class GuiLoggingHandler(logging.Handler):
    def __init__(self, slot_emitter):
        super().__init__()
        self.slot_emitter = slot_emitter

    def emit(self, record):
        log_entry = self.format(record)
        self.slot_emitter.log_signal.emit(log_entry)

class Emitter(QObject):
    log_signal = Signal(str)

class OpcUaClientGui(QMainWindow):
    def __init__(self, client_logic: OpcUaClientLogic):
        super().__init__()
        self.client_logic = client_logic
        self.current_device_addr = None

        self.setWindowTitle("OPC-UA MUX Client")
        self.setGeometry(100, 100, 900, 600)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)

        self._create_connection_ui()
        main_splitter = QHBoxLayout()
        self._create_device_list_ui(main_splitter)
        self._create_device_control_ui(main_splitter)
        self.main_layout.addLayout(main_splitter)
        self._create_logging_ui()
        self.set_ui_disconnected_state()

    def _create_connection_ui(self):
        conn_box = QHBoxLayout()
        self.url_label = QLabel("Server URL:")
        
        url_string = self.client_logic.endpoint_url 
        self.url_input = QLineEdit(url_string)
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        
        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        
        conn_box.addWidget(self.url_label)
        conn_box.addWidget(self.url_input, 1)
        conn_box.addWidget(self.connect_button)
        conn_box.addWidget(self.status_label)
        
        # --- NEW: Add MUX count display ---
        conn_box.addStretch() # Add a flexible spacer
        conn_box.addWidget(QLabel("MUX Board Count:"))
        self.mux_count_label = QLabel("N/A")
        self.mux_count_label.setStyleSheet("font-weight: bold;")
        conn_box.addWidget(self.mux_count_label)
        
        self.main_layout.addLayout(conn_box)

    def _create_device_list_ui(self, parent_layout):
        # This method is unchanged
        list_box = QVBoxLayout()
        list_box.addWidget(QLabel("Discovered Devices"))
        self.device_list = QListWidget()
        self.device_list.currentItemChanged.connect(self.on_device_selected)
        
        self.rescan_button = QPushButton("Rescan Hardware")
        self.rescan_button.clicked.connect(self.rescan_hardware)

        list_box.addWidget(self.device_list)
        list_box.addWidget(self.rescan_button)
        parent_layout.addLayout(list_box, 1)

    def _create_device_control_ui(self, parent_layout):
        # This method is unchanged
        self.control_area = QWidget()
        control_layout = QVBoxLayout(self.control_area)
        control_layout.addWidget(QLabel("Device Control Panel"))

        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Active Channel:"))
        self.active_channel_label = QLabel("N/A")
        self.active_channel_label.setStyleSheet("font-weight: bold;")
        channel_layout.addStretch()
        channel_layout.addWidget(self.active_channel_label)
        control_layout.addLayout(channel_layout)
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Last Operation Status:"))
        self.last_status_label = QLabel("N/A")
        self.last_status_label.setStyleSheet("font-style: italic;")
        status_layout.addStretch()
        status_layout.addWidget(self.last_status_label)
        control_layout.addLayout(status_layout)
        control_layout.addWidget(QFrame(self))
        set_channel_layout = QHBoxLayout()
        set_channel_layout.addWidget(QLabel("Set New Channel (0-255):"))
        self.channel_spinbox = QSpinBox()
        self.channel_spinbox.setRange(0, 255)
        self.set_channel_button = QPushButton("Set Channel")
        self.set_channel_button.clicked.connect(self.set_channel)
        set_channel_layout.addWidget(self.channel_spinbox)
        set_channel_layout.addWidget(self.set_channel_button)
        control_layout.addLayout(set_channel_layout)
        self.reset_button = QPushButton("Reset Mux")
        self.reset_button.clicked.connect(self.reset_mux)
        control_layout.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignRight)
        control_layout.addStretch()
        parent_layout.addWidget(self.control_area, 2)

    def _create_logging_ui(self):
        # This method is unchanged
        log_box = QVBoxLayout()
        log_box.addWidget(QLabel("Logs"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        log_box.addWidget(self.log_output)
        self.main_layout.addLayout(log_box)

        self.log_emitter = Emitter()
        self.log_emitter.log_signal.connect(self.log_output.append)
        gui_handler = GuiLoggingHandler(self.log_emitter)
        
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        logging.getLogger().addHandler(gui_handler)
        logging.getLogger("asyncua").setLevel(logging.WARNING)

    def set_ui_disconnected_state(self):
        self.connect_button.setText("Connect")
        self.url_input.setEnabled(True)
        self.status_label.setText("Status: Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.device_list.clear()
        self.rescan_button.setEnabled(False)
        self.control_area.setEnabled(False)
        self.active_channel_label.setText("N/A")
        self.last_status_label.setText("N/A")
        # --- NEW: Reset MUX count label on disconnect ---
        self.mux_count_label.setText("N/A")

    def set_ui_connected_state(self):
        self.connect_button.setText("Disconnect")
        self.url_input.setEnabled(False)
        self.status_label.setText("Status: Connected")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self.rescan_button.setEnabled(True)

    @asyncSlot()
    async def toggle_connection(self):
        if self.client_logic.client:
            await self.disconnect_from_server()
        else:
            await self.connect_to_server()

    async def connect_to_server(self):
        self.status_label.setText("Status: Connecting...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.connect_button.setEnabled(False)
        
        server_url = self.url_input.text()
        is_connected = await self.client_logic.connect(server_url)
        
        if is_connected:
            self.set_ui_connected_state()
            await self.client_logic.find_gateway_and_methods()
            await self.populate_device_list()
            # --- NEW: Update the count after connecting ---
            await self.update_mux_count()
        else:
            self.set_ui_disconnected_state()
        
        self.connect_button.setEnabled(True)

    async def disconnect_from_server(self):
        await self.client_logic.disconnect()
        self.set_ui_disconnected_state()

    async def populate_device_list(self):
        self.device_list.clear()
        self.control_area.setEnabled(False)
        logging.info("Discovering devices...")
        device_addrs = await self.client_logic.discover_devices()
        if device_addrs:
            self.device_list.addItems(device_addrs)
            logging.info(f"Found devices: {device_addrs}")
        else:
            logging.warning("No devices found.")

    # --- NEW: Helper method to update the count display ---
    async def update_mux_count(self):
        """Reads the MUX count from the logic layer and updates the GUI."""
        logging.info("Reading MUX board count...")
        count = await self.client_logic.read_mux_count()
        if count is not None:
            self.mux_count_label.setText(str(count))
            logging.info(f"Server reports {count} MUX boards.")
        else:
            self.mux_count_label.setText("Error")
            logging.error("Failed to read MUX board count.")

    @asyncSlot()
    async def on_device_selected(self, current_item, previous_item):
        if current_item is None:
            self.current_device_addr = None
            self.control_area.setEnabled(False)
            return
        self.current_device_addr = current_item.text()
        self.control_area.setEnabled(True)
        logging.info(f"Selected device: {self.current_device_addr}")
        await self.update_device_details()

    async def update_device_details(self):
        if not self.current_device_addr: return
        state = await self.client_logic.read_device_state(self.current_device_addr)
        if state:
            channel, status = state
            self.active_channel_label.setText(str(channel))
            self.last_status_label.setText(status)
        else:
            self.active_channel_label.setText("Error")
            self.last_status_label.setText("Error reading state")

    @asyncSlot()
    async def set_channel(self):
        if not self.current_device_addr: return
        channel_to_set = self.channel_spinbox.value()
        logging.info(f"Writing {channel_to_set} to SetChannel on {self.current_device_addr}")
        success = await self.client_logic.write_channel(self.current_device_addr, channel_to_set)
        if not success:
            logging.error(f"Failed to write channel for {self.current_device_addr}.")
        await asyncio.sleep(0.5) # A slightly longer sleep to ensure server has time to update
        await self.update_device_details()

    @asyncSlot()
    async def reset_mux(self):
        # --- REWORKED: This method is now updated ---
        if not self.current_device_addr: return
        logging.info(f"Triggering Reset on {self.current_device_addr}")
        # 1. Call the new logic method
        success = await self.client_logic.trigger_reset_mux(self.current_device_addr)
        
        # 2. Check the boolean result
        if success:
            logging.info(f"Reset command sent successfully to {self.current_device_addr}.")
        else:
            logging.error(f"Failed to send Reset command to {self.current_device_addr}.")
            
        await asyncio.sleep(0.5) # A slightly longer sleep to ensure server has time to update
        await self.update_device_details()

    @asyncSlot()
    async def rescan_hardware(self):
        logging.info("Calling RescanHardware on server...")
        await self.client_logic.call_rescan_hardware()
        logging.info("Rescan complete. Refreshing device list.")
        await self.populate_device_list()
        await self.update_mux_count()