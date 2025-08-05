import asyncio
from qasync import asyncSlot
import logging
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QSpinBox, QFrame, QTextEdit
from PySide6.QtCore import Qt, Signal, QObject

# Assuming clientLogic.py is in the same directory or a reachable path
from src.opc_ua.clientLogic import OpcUaClientLogic

# --- Logging Setup ---
# A custom handler to emit logs to the GUI's text box
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
        conn_box.addWidget(self.url_input, 1) # The '1' gives the input field priority to stretch
        conn_box.addWidget(self.connect_button)
        conn_box.addWidget(self.status_label)
        self.main_layout.addLayout(conn_box)

    def _create_device_list_ui(self, parent_layout):
        list_box = QVBoxLayout()
        list_box.addWidget(QLabel("Discovered Devices"))
        self.device_list = QListWidget()
        # The connection now points to the decorated async method
        self.device_list.currentItemChanged.connect(self.on_device_selected)
        
        self.rescan_button = QPushButton("Rescan Hardware")
        # The connection now points to the decorated async method
        self.rescan_button.clicked.connect(self.rescan_hardware)

        list_box.addWidget(self.device_list)
        list_box.addWidget(self.rescan_button)
        parent_layout.addLayout(list_box, 1)

    def _create_device_control_ui(self, parent_layout):
        self.control_area = QWidget()
        control_layout = QVBoxLayout(self.control_area)
        control_layout.addWidget(QLabel("Device Control Panel"))

        # ... (No changes to the layout creation itself)
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
        set_channel_layout.addWidget(QLabel("Set New Channel (1-8):"))
        self.channel_spinbox = QSpinBox()
        self.channel_spinbox.setRange(0, 255)
        self.set_channel_button = QPushButton("Set Channel")
        # The connection now points to the decorated async method
        self.set_channel_button.clicked.connect(self.set_channel)
        set_channel_layout.addWidget(self.channel_spinbox)
        set_channel_layout.addWidget(self.set_channel_button)
        control_layout.addLayout(set_channel_layout)
        self.reset_button = QPushButton("Reset Mux")
        # The connection now points to the decorated async method
        self.reset_button.clicked.connect(self.reset_mux)
        control_layout.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignRight)
        control_layout.addStretch()
        parent_layout.addWidget(self.control_area, 2)

    def _create_logging_ui(self):
        log_box = QVBoxLayout()
        log_box.addWidget(QLabel("Logs"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        log_box.addWidget(self.log_output)
        self.main_layout.addLayout(log_box)

        # --- MODIFIED LOGGING SETUP ---
        # 1. Create the emitter and handler as before
        self.log_emitter = Emitter()
        self.log_emitter.log_signal.connect(self.log_output.append)
        gui_handler = GuiLoggingHandler(self.log_emitter)
        
        # 2. Set a formatter for this specific handler
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

        # 3. Add the handler to the root logger.
        # DO NOT configure the root logger's level here anymore.
        logging.getLogger().addHandler(gui_handler)
        
        # Also set the asyncua logger level to avoid spam
        logging.getLogger("asyncua").setLevel(logging.WARNING)

    def set_ui_disconnected_state(self):
        # ... (No changes in this method)
        self.connect_button.setText("Connect")
        self.url_input.setEnabled(True)
        self.status_label.setText("Status: Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.device_list.clear()
        self.rescan_button.setEnabled(False)
        self.control_area.setEnabled(False)
        self.active_channel_label.setText("N/A")
        self.last_status_label.setText("N/A")

    def set_ui_connected_state(self):
        # ... (No changes in this method)
        self.connect_button.setText("Disconnect")
        self.url_input.setEnabled(False)
        self.status_label.setText("Status: Connected")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self.rescan_button.setEnabled(True)

    # --- ASYNC SLOTS (MODIFIED) ---
    @asyncSlot()
    async def toggle_connection(self):
        # This check is now simpler and more robust
        if self.client_logic.client:
            await self.disconnect_from_server()
        else:
            await self.connect_to_server()

    async def connect_to_server(self):
        self.status_label.setText("Status: Connecting...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.connect_button.setEnabled(False)
        
        # Pass the URL from the text input to the connect method
        server_url = self.url_input.text()
        is_connected = await self.client_logic.connect(server_url)
        
        if is_connected:
            self.set_ui_connected_state()
            await self.client_logic.find_gateway_and_methods()
            await self.populate_device_list()
        else:
            self.set_ui_disconnected_state()
        
        self.connect_button.setEnabled(True)


    # These are helper methods called by other async methods, so they don't need the decorator
    async def connect_to_server(self):
        self.status_label.setText("Status: Connecting...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.connect_button.setEnabled(False)
        
        # Get the URL from the GUI's text input
        server_url = self.url_input.text()
        is_connected = await self.client_logic.connect(server_url)
        
        if is_connected:
            self.set_ui_connected_state()
            # These calls are correct and should remain
            await self.client_logic.find_gateway_and_methods()
            await self.populate_device_list()
        else:
            self.set_ui_disconnected_state()
        
        self.connect_button.setEnabled(True)


    async def disconnect_from_server(self):
        # This now calls the new, more thorough disconnect logic
        await self.client_logic.disconnect()
        self.set_ui_disconnected_state()

    async def populate_device_list(self):
        # ... (No changes in this method)
        self.device_list.clear()
        self.control_area.setEnabled(False)
        logging.info("Discovering devices...")
        device_addrs = await self.client_logic.discover_devices()
        if device_addrs:
            self.device_list.addItems(device_addrs)
            logging.info(f"Found devices: {device_addrs}")
        else:
            logging.warning("No devices found.")

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
        # ... (No changes in this method)
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
        logging.info(f"Calling SetChannel({channel_to_set}) on {self.current_device_addr}")
        await self.client_logic.write_channel(self.current_device_addr, channel_to_set)
        await asyncio.sleep(0.1)
        await self.update_device_details()

    @asyncSlot()
    async def reset_mux(self):
        if not self.current_device_addr: return
        logging.info(f"Calling Reset() on {self.current_device_addr}")
        result = await self.client_logic.call_reset_mux(self.current_device_addr)
        logging.info(f"Reset method returned: {result}")
        await asyncio.sleep(0.1)
        await self.update_device_details()

    @asyncSlot()
    async def rescan_hardware(self):
        logging.info("Calling RescanHardware on server...")
        await self.client_logic.call_rescan_hardware()
        logging.info("Rescan complete. Refreshing device list.")
        await self.populate_device_list()