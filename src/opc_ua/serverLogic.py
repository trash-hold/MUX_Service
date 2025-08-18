import asyncio
import logging
import contextlib
from asyncua import Server, ua
from asyncua.common.methods import uamethod

# Assuming DeviceController is in this path, adjust if necessary
from src.communicator.deviceCommincator import DeviceController, MuxDevice

class SubHandler:
    def __init__(self, server_logic):
        self.server_logic = server_logic

    async def datachange_notification(self, node, val, data):
        if not self.server_logic.is_running:
            return

        try:
            parent_node = await self.server_logic.server.get_node(node).get_parent()
            node_name = (await node.read_browse_name()).Name

            if node_name == "SetChannel":
                await self.server_logic._handle_set_channel_event(parent_node, node, val)
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
        self.gateway_status_var = None
        
        self.nodes_to_monitor = []
        self.is_running = False
        self._reconnect_task = None

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

        active_ch_var = await mux_obj.add_variable(self.idx, "ActiveChannel", device_state.active_channel, ua.VariantType.Int32)
        await active_ch_var.set_writable(False)
        status_op_var = await mux_obj.add_variable(self.idx, "LastOperationStatus", device_state.last_status)
        await status_op_var.set_writable(False)

        set_ch_var = await mux_obj.add_variable(self.idx, "SetChannel", 0, ua.VariantType.Int32)
        await set_ch_var.set_writable(True)
        reset_var = await mux_obj.add_variable(self.idx, "Reset", False, ua.VariantType.Boolean)
        await reset_var.set_writable(True)

        self.nodes_to_monitor.append(set_ch_var)
        self.nodes_to_monitor.append(reset_var)
        self.mux_nodes[address] = mux_obj
        await self._update_mux_count()

    async def _initial_scan_and_populate(self):
        logging.info("Performing initial hardware scan...")
        if not self.controller.is_connected:
            logging.warning("Cannot scan, device is not connected.")
            await self._update_gateway_status("Disconnected")
            return

        found_devices = self.controller.scan_for_devices()
        if not found_devices:
            logging.warning("Initial scan found no devices.")
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
        self.gateway_status_var = await self.gateway_node.add_variable(self.idx, "GatewayStatus", "Initializing", ua.VariantType.String)
        await self.gateway_status_var.set_writable(False)
        
        self.mux_count_var = await self.gateway_node.add_variable(self.idx, "MuxBoardCount", 0, ua.VariantType.UInt32)
        await self.mux_count_var.set_writable(False)
        await self.gateway_node.add_method(self.idx, "RescanHardware", self._rescan_handler)

        await self.server.start()
        logging.info(f"OPC UA server is live at {self.config['endpoint']}")
        
        await self._update_gateway_status("Connected" if self.controller.is_connected else "Disconnected")
        await self._initial_scan_and_populate()
        
        handler = SubHandler(self)
        sub = await self.server.create_subscription(500, handler)
        
        if self.nodes_to_monitor:
            await sub.subscribe_data_change(self.nodes_to_monitor)
            logging.info(f"Server subscribed to data changes for {len(self.nodes_to_monitor)} trigger nodes.")

        self.is_running = True
        self._reconnect_task = asyncio.create_task(self._connection_monitor())
        logging.info("Server startup complete. Running indefinitely...")

    async def stop(self):
        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
        
        if self.server and self.server.bserver:
            await self.server.stop()
            logging.info("OPC UA server stopped.")

    async def _connection_monitor(self):
        """Periodically checks connection and attempts to reconnect if needed."""
        while True:
            await asyncio.sleep(10) # Check every 10 seconds
            if not self.controller.is_connected:
                logging.warning("Device disconnected. Attempting to reconnect...")
                await self._update_gateway_status("Reconnecting")
                if self.controller.connect():
                    logging.info("Successfully reconnected to device.")
                    await self._update_gateway_status("Connected")
                    # Optionally trigger a rescan after reconnecting
                    await self._rescan_handler(self.gateway_node.nodeid) 
                else:
                    await self._update_gateway_status("Disconnected")


    async def _handle_set_channel_event(self, parent_node, trigger_node, val):
        """Handles the logic for a SetChannel write event."""
        parent_name = (await parent_node.read_browse_name()).Name
        
        # A value of 0 can be considered a "no-op" or reset, so we ignore it.
        if val == 0:
            return
            
        try:
            address = int(parent_name.split('_')[1], 16)
            current_state = self.controller.devices.get(address)

            if not current_state:
                logging.warning(f"Received set channel for unknown device {parent_name}. Ignoring.")
                return

            # This check is still useful to prevent spamming the same command repeatedly
            # without an intervening reset.
            if val == current_state.active_channel:
                logging.debug(f"Ignoring redundant SetChannel for {parent_name} to value {val}.")
                await trigger_node.write_value(ua.Variant(0, ua.VariantType.Int32))
                return

            logging.info(f"Write event on {parent_name}: SetChannel to {val}")
            if self.controller.set_channel(address, val):
                await self._update_mux_variables(address)
            else:
                logging.error(f"Failed to set channel for {parent_name}. Device disconnected.")
                await self._update_mux_variables(address)

        except Exception as e:
            logging.error(f"Error processing SetChannel for {parent_name}: {e}")
        finally:
            # This ensures the next write of the same value will trigger an event.
            logging.debug(f"Resetting SetChannel trigger for {parent_name} back to 0.")
            await trigger_node.write_value(ua.Variant(0, ua.VariantType.Int32))


    async def _handle_reset_event(self, parent_node, trigger_node, val):
        if not val:
            return
        parent_name = (await parent_node.read_browse_name()).Name
        try:
            address = int(parent_name.split('_')[1], 16)
            logging.info(f"Write event on {parent_name}: Reset triggered.")
            if self.controller.reset_mux(address):
                await self._update_mux_variables(address)
            else:
                logging.error(f"Failed to reset {parent_name}. Device disconnected.")
                await self._update_mux_variables(address) # Update with error status
        
        except Exception as e:
            logging.error(f"Error processing Reset for {parent_name}: {e}")
        finally:
            await trigger_node.write_value(False)

    async def _update_mux_variables(self, address: int):
        if address in self.mux_nodes and address in self.controller.devices:
            device_state = self.controller.devices[address]
            mux_node = self.mux_nodes[address]
            
            channel_node = await mux_node.get_child(f"{self.idx}:ActiveChannel")
            await channel_node.write_value(ua.Variant(device_state.active_channel, ua.VariantType.Int32))
            
            status_node = await mux_node.get_child(f"{self.idx}:LastOperationStatus")
            await status_node.write_value(device_state.last_status)

    async def _update_mux_count(self):
        """Updates the MuxBoardCount variable on the server."""
        if self.mux_count_var:
            count = len(self.mux_nodes)
            await self.mux_count_var.write_value(ua.Variant(count, ua.VariantType.UInt32))

    async def _update_gateway_status(self, status: str):
        if self.gateway_status_var:
            await self.gateway_status_var.write_value(status)
            logging.info(f"Gateway status updated to: {status}")

    @uamethod
    async def _rescan_handler(self, parent):
        logging.warning("Rescan requested. A server restart is still the safest method for hardware changes.")
        event_generator = await self.server.get_event_generator()
        await event_generator.trigger(message="Rescan requested. Note: Dynamic node removal is not supported; restart is recommended for hardware removal.")
        
        # Perform a non-blocking scan to add new devices
        logging.info("Scanning for new devices...")
        found_devices = self.controller.scan_for_devices()
        if not found_devices:
            logging.info("Rescan found no new devices.")
            return
        
        new_devices_added = 0
        for addr in found_devices:
            if addr not in self.mux_nodes:
                logging.info(f"Rescan found new device at {hex(addr)}. Adding node.")
                await self._create_mux_node(addr)
                self.controller.reset_mux(addr)
                await self._update_mux_variables(addr)
                new_devices_added += 1
        
        if new_devices_added > 0:
            logging.info(f"Added {new_devices_added} new device(s). Subscriptions must be re-initialized by restarting the server to make them active.")
        
        logging.info("Rescan handler complete.")