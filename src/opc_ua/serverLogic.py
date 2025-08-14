import asyncio
import logging
from asyncua import Server, ua

# It's good practice to keep uamethod for other potential methods,
# but it's not strictly needed if you remove all methods.
from asyncua.common.methods import uamethod

from src.communicator.deviceCommincator import DeviceController, MuxDevice

class OpcUaServer:
    def __init__(self, controller: DeviceController, config: dict):
        self.controller = controller
        self.config = config
        self.server = Server()
        self.idx = 0
        self.mux_nodes = {}
        self.gateway_node = None
        # Add a variable to hold the MUX count
        self.mux_count_var = None

    async def _initialize_server(self):
        await self.server.init()
        self.server.set_endpoint(self.config['endpoint'])
        self.server.set_server_name(self.config['name'])
        uri = self.config['namespace_uri']
        self.idx = await self.server.register_namespace(uri)

    async def _create_mux_node(self, address: int):
        if address in self.mux_nodes:
            return

        addr_str = hex(address)
        logging.info(f"Creating OPC UA object for MUX at address {addr_str}")

        mux_obj = await self.gateway_node.add_object(self.idx, f"Mux_{addr_str}")
        device_state = self.controller.devices.get(address, MuxDevice(address))

        # This variable remains read-only for clients.
        active_ch_var = await mux_obj.add_variable(self.idx, "ActiveChannel", device_state.active_channel, ua.VariantType.Byte)
        await active_ch_var.set_writable(False)

        status_op_var = await mux_obj.add_variable(self.idx, "LastOperationStatus", device_state.last_status)
        await status_op_var.set_writable(False) # Status should be read-only for the client

        # --- REWORK: Replace SetChannel method with a writable variable ---
        # This variable is what the client will write to.
        set_ch_var = await mux_obj.add_variable(self.idx, "SetChannel", 0, ua.VariantType.Byte)
        await set_ch_var.set_writable(True)
        # Add a callback for when the client writes to this variable
        self.server.subscribe_data_change(set_ch_var, self._set_channel_handler)

        # --- REWORK: Replace Reset method with a writable variable ---
        # Client writes a '1' to this variable to trigger a reset.
        reset_var = await mux_obj.add_variable(self.idx, "Reset", 0, ua.VariantType.Boolean)
        await reset_var.set_writable(True)
        # Add a callback for the reset trigger
        self.server.subscribe_data_change(reset_var, self._reset_handler)

        self.mux_nodes[address] = mux_obj
        # Update the MUX count after adding a node
        await self._update_mux_count()

    async def _initial_scan_and_populate(self):
        logging.info("Performing initial hardware scan via controller...")
        found_devices = self.controller.scan_for_devices()
        if not found_devices:
            # Still update the count even if no devices are found
            await self._update_mux_count()
            return

        for addr in found_devices:
            await self._create_mux_node(addr)
            logging.info(f"Sending initial RESET command to MUX at {hex(addr)}")
            self.controller.reset_mux(addr)
            # Update the node values after reset
            await self._update_mux_variables(addr)

    async def start(self):
        await self._initialize_server()
        self.gateway_node = await self.server.nodes.objects.add_object(self.idx, "ArduinoGateway")
        await self.gateway_node.add_variable(self.idx, "GatewayStatus", "Connected", ua.VariantType.String)

        # --- NEW: Add the MUX count variable ---
        self.mux_count_var = await self.gateway_node.add_variable(self.idx, "MuxBoardCount", 0, ua.VariantType.UInt32)
        await self.mux_count_var.set_writable(False)

        # Keep the rescan method as it's useful for system management
        await self.gateway_node.add_method(self.idx, "RescanHardware", self._rescan_handler)

        await self.server.start()
        logging.info(f"OPC UA server is live at {self.config['endpoint']}")
        await self._initial_scan_and_populate()
        logging.info("Initial device population complete.")

    async def stop(self):
        # Check if the server object exists AND its internal binary server has been initialized.
        # self.server.bserver is only created after a successful server.init() call inside start().
        if self.server and self.server.bserver:
            await self.server.stop()
            logging.info("OPC UA server stopped.")
        else:
            logging.info("OPC UA server was not running, no need to stop.")

    # --- REWORK: Data change handler for SetChannel variable ---
    async def _set_channel_handler(self, node, val, data):
        """Handles data change events for the SetChannel variable."""
        try:
            # Get the parent MUX object from the node that changed
            parent_node = await self.server.get_node(node).get_parent()
            parent_name = (await parent_node.read_browse_name()).Name
            address = int(parent_name.split('_')[1], 16)

            logging.info(f"Write detected on {parent_name}: SetChannel to {val}")

            # 1. Command the hardware
            self.controller.set_channel(address, val)

            # 2. Update the OPC UA variables to reflect the new state
            await self._update_mux_variables(address)

        except Exception as e:
            logging.error(f"Error in SetChannel handler for {parent_name}: {e}")

    # --- REWORK: Data change handler for Reset variable ---
    async def _reset_handler(self, node, val, data):
        """Handles data change events for the Reset variable."""
        # Only trigger on a 'True' or '1' value to prevent accidental resets
        if not val:
            return
        try:
            parent_node = await self.server.get_node(node).get_parent()
            parent_name = (await parent_node.read_browse_name()).Name
            address = int(parent_name.split('_')[1], 16)

            logging.info(f"Write detected on {parent_name}: Reset triggered.")

            # 1. Command the hardware
            self.controller.reset_mux(address)

            # 2. Update the OPC UA variables
            await self._update_mux_variables(address)

            # 3. Reset the trigger variable back to False
            await self.server.get_node(node).write_value(False)

        except Exception as e:
            logging.error(f"Error in Reset handler for {parent_name}: {e}")

    # --- HELPER: A single function to update MUX variables ---
    async def _update_mux_variables(self, address: int):
        """Updates the OPC UA variables for a given MUX from the controller state."""
        if address in self.mux_nodes:
            device_state = self.controller.devices[address]
            mux_node = self.mux_nodes[address]

            # Update ActiveChannel
            channel_node = await mux_node.get_child(f"{self.idx}:ActiveChannel")
            await channel_node.write_value(ua.Variant(device_state.active_channel, ua.VariantType.Byte))

            # Update LastOperationStatus
            status_node = await mux_node.get_child(f"{self.idx}:LastOperationStatus")
            await status_node.write_value(device_state.last_status)

    # --- HELPER: Update the MUX count ---
    async def _update_mux_count(self):
        """Updates the MuxBoardCount variable."""
        if self.mux_count_var:
            count = len(self.mux_nodes)
            await self.mux_count_var.write_value(count)

    @uamethod
    async def _rescan_handler(self, parent):
        logging.info("Method call: Relaying rescan request to DeviceController...")
        existing_addrs_set = set(self.mux_nodes.keys())
        found_addrs_set = set(self.controller.scan_for_devices())

        addrs_to_add = found_addrs_set - existing_addrs_set
        addrs_to_remove = existing_addrs_set - found_addrs_set

        for addr in addrs_to_add:
            await self._create_mux_node(addr)

        for addr in addrs_to_remove:
            if addr in self.mux_nodes:
                node_to_delete = self.mux_nodes.pop(addr)
                await self.server.delete_nodes([node_to_delete], recursive=True)
                logging.info(f"Removed node for disconnected MUX at address {hex(addr)}")
        
        # Update the count after adding/removing nodes
        await self._update_mux_count()

        event_generator = await self.server.get_event_generator()
        await event_generator.trigger(message="Address space updated after hardware rescan.")
        logging.info("Rescan complete.")