import asyncio
import logging
from asyncua import Server, ua
from asyncua.common.methods import uamethod

from src.communicator.deviceCommincator import DeviceController, MuxDevice

# --- NEW: Subscription Handler Class ---
# This class is the standard way to receive data change notifications in asyncua.
class SubHandler:
    def __init__(self, server_logic):
        # Give the handler a reference back to the main OpcUaServer logic
        # so it can call controller methods and update other nodes.
        self.server_logic = server_logic

    async def datachange_notification(self, node, val, data):
        if not self.server_logic.is_running:
            return  # Ignore initial data change notifications during startup

        try:
            parent_node = await self.server_logic.server.get_node(node).get_parent()
            node_name = (await node.read_browse_name()).Name

            if node_name == "SetChannel":
                await self.server_logic._handle_set_channel_event(parent_node, val)
            elif node_name == "Reset":
                await self.server_logic._handle_reset_event(parent_node, node, val)

        except Exception as e:
            logging.error(f"Error in datachange_notification for node {node}: {e}", exc_info=True)

class OpcUaServer:
    def __init__(self, controller: DeviceController, config: dict):
        self.controller = controller
        self.config = config
        self.server = Server()
        self.idx = 0
        self.mux_nodes = {}
        self.gateway_node = None
        self.mux_count_var = None
        
        self.nodes_to_monitor = []
        self.is_running = False

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

        # Read-only variables
        active_ch_var = await mux_obj.add_variable(self.idx, "ActiveChannel", device_state.active_channel, ua.VariantType.Byte)
        await active_ch_var.set_writable(False)
        status_op_var = await mux_obj.add_variable(self.idx, "LastOperationStatus", device_state.last_status)
        await status_op_var.set_writable(False)

        # Writable variables that will trigger actions
        set_ch_var = await mux_obj.add_variable(self.idx, "SetChannel", 0, ua.VariantType.Byte)
        await set_ch_var.set_writable(True)
        
        reset_var = await mux_obj.add_variable(self.idx, "Reset", False, ua.VariantType.Boolean)
        await reset_var.set_writable(True)

        # --- REWORK: Add the trigger nodes to a list for later subscription ---
        # The incorrect callback calls are removed.
        self.nodes_to_monitor.append(set_ch_var)
        self.nodes_to_monitor.append(reset_var)

        self.mux_nodes[address] = mux_obj
        await self._update_mux_count()

    async def _initial_scan_and_populate(self):
        logging.info("Performing initial hardware scan via controller...")
        found_devices = self.controller.scan_for_devices()
        if not found_devices:
            await self._update_mux_count()
            return

        for addr in found_devices:
            await self._create_mux_node(addr)
            logging.info(f"Sending initial RESET command to MUX at {hex(addr)}")
            self.controller.reset_mux(addr)
            await self._update_mux_variables(addr)

    async def start(self):
        await self._initialize_server()
        self.gateway_node = await self.server.nodes.objects.add_object(self.idx, "ArduinoGateway")
        await self.gateway_node.add_variable(self.idx, "GatewayStatus", "Connected", ua.VariantType.String)
        self.mux_count_var = await self.gateway_node.add_variable(self.idx, "MuxBoardCount", 0, ua.VariantType.UInt32)
        await self.mux_count_var.set_writable(False)
        await self.gateway_node.add_method(self.idx, "RescanHardware", self._rescan_handler)

        await self.server.start()
        logging.info(f"OPC UA server is live at {self.config['endpoint']}")
        
        # Populate nodes before subscribing
        await self._initial_scan_and_populate()
        
        # --- NEW: Create the internal subscription after the server starts ---
        handler = SubHandler(self)
        sub = await self.server.create_subscription(500, handler) # 500ms reporting interval
        
        # Subscribe to the Value attribute of all collected nodes
        if self.nodes_to_monitor:
            await sub.subscribe_data_change(self.nodes_to_monitor)
            logging.info(f"Server subscribed to data changes for {len(self.nodes_to_monitor)} trigger nodes.")

        logging.info("Initial device population complete.")
        self.is_running = True
        logging.info("Server is now fully running and will process client commands.")

    async def stop(self):
        if self.server and self.server.bserver:
            await self.server.stop()
            logging.info("OPC UA server stopped.")
        else:
            logging.info("OPC UA server was not running, no need to stop.")

    async def _handle_set_channel_event(self, parent_node, val):
        parent_name = (await parent_node.read_browse_name()).Name
        try:
            address = int(parent_name.split('_')[1], 16)
            
            # Get the current state from the controller (our source of truth for hardware)
            current_state = self.controller.devices.get(address)
            if not current_state:
                logging.warning(f"Received set channel event for unknown device {parent_name}. Ignoring.")
                return

            # Only send a command if the requested value is different from the current known state.
            if val == current_state.active_channel:
                logging.debug(f"Ignoring redundant SetChannel event for {parent_name} to value {val}.")
                return

            logging.info(f"Write event on {parent_name}: SetChannel to {val}")
            self.controller.set_channel(address, val)
            await self._update_mux_variables(address)
        except Exception as e:
            logging.error(f"Error processing SetChannel event for {parent_name}: {e}")


    async def _handle_reset_event(self, parent_node, trigger_node, val):
        """Handles the logic for a Reset write event."""
        if not val: # Only act when value is True
            return
        parent_name = (await parent_node.read_browse_name()).Name
        try:
            address = int(parent_name.split('_')[1], 16)
            logging.info(f"Write event on {parent_name}: Reset triggered.")
            self.controller.reset_mux(address)
            await self._update_mux_variables(address)
            # IMPORTANT: Reset the trigger variable back to False
            await trigger_node.write_value(False)
        except Exception as e:
            logging.error(f"Error processing Reset event for {parent_name}: {e}")

    # --- Helper functions remain the same ---
    async def _update_mux_variables(self, address: int):
        if address in self.mux_nodes:
            device_state = self.controller.devices[address]
            mux_node = self.mux_nodes[address]
            channel_node = await mux_node.get_child(f"{self.idx}:ActiveChannel")
            await channel_node.write_value(ua.Variant(device_state.active_channel, ua.VariantType.Byte))
            status_node = await mux_node.get_child(f"{self.idx}:LastOperationStatus")
            await status_node.write_value(device_state.last_status)

    async def _update_mux_count(self):
        if self.mux_count_var:
            count = len(self.mux_nodes)
            await self.mux_count_var.write_value(ua.Variant(count, ua.VariantType.UInt32))

    @uamethod
    async def _rescan_handler(self, parent):
        # NOTE: A dynamic rescan that adds/removes nodes requires complex subscription management.
        # For now, we will log a message advising a restart, which is a safe approach.
        logging.warning("Rescan requested. A server restart is recommended to apply hardware changes and re-initialize subscriptions correctly.")
        event_generator = await self.server.get_event_generator()
        await event_generator.trigger(message="Rescan requested. Server restart recommended to apply changes.")
        logging.info("Rescan handler complete.")