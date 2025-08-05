import asyncio
import logging
from asyncua import Server, ua
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
        
        # Variable is now READ-ONLY for clients. Its value is only changed by server methods.
        active_ch_var = await mux_obj.add_variable(self.idx, "ActiveChannel", device_state.active_channel, ua.VariantType.Byte)
        await active_ch_var.set_writable(False)

        status_op_var = await mux_obj.add_variable(self.idx, "LastOperationStatus", device_state.last_status)
        
        # Add the existing Reset method
        await mux_obj.add_method(self.idx, "Reset", self._reset_handler, [], [ua.VariantType.String])

        # --- THE FIX: Add a new method for setting the channel ---
        # Define the input argument for the method (a single byte)
        in_arg = ua.Argument(
            Name="Channel",
            DataType=ua.NodeId(ua.ObjectIds.Byte),
            ValueRank=-1,
            ArrayDimensions=[],
            Description=ua.LocalizedText("Channel to set (0-255)")
        )
        # Add the method to the MUX object
        await mux_obj.add_method(self.idx, "SetChannel", self._set_channel_handler, [in_arg], [ua.VariantType.String])
        
        self.mux_nodes[address] = mux_obj

    async def _initial_scan_and_populate(self):
        logging.info("Performing initial hardware scan via controller...")
        found_devices = self.controller.scan_for_devices()
        if not found_devices:
            return

        for addr in found_devices:
            await self._create_mux_node(addr)
            logging.info(f"Sending initial RESET command to MUX at {hex(addr)}")
            self.controller.reset_mux(addr)
            status_node = await self.mux_nodes[addr].get_child(f"{self.idx}:LastOperationStatus")
            await status_node.write_value(self.controller.devices[addr].last_status)

    async def start(self):
        await self._initialize_server()
        self.gateway_node = await self.server.nodes.objects.add_object(self.idx, "ArduinoGateway")
        await self.gateway_node.add_variable(self.idx, "GatewayStatus", "Connected", ua.VariantType.String)
        await self.gateway_node.add_method(self.idx, "RescanHardware", self._rescan_handler)
        await self.server.start()
        logging.info(f"OPC UA server is live at {self.config['endpoint']}")
        await self._initial_scan_and_populate()
        logging.info("Initial device population complete.")

    async def stop(self):
        if self.server:
            await self.server.stop()

    # --- NEW METHOD HANDLER ---
    @uamethod
    async def _set_channel_handler(self, parent, channel: int):
        """Handles the client call to the SetChannel method."""
        parent_node = self.server.get_node(parent)
        parent_name = (await parent_node.read_browse_name()).Name
        try:
            address = int(parent_name.split('_')[1], 16)
            logging.info(f"Method call: SetChannel on {parent_name} to {channel}")

            # 1. Command the hardware
            self.controller.set_channel(address, channel)
            device_state = self.controller.devices[address]

            # 2. Update the read-only variable to reflect the new state
            channel_node = await parent_node.get_child(f"{self.idx}:ActiveChannel")
            await channel_node.write_value(ua.Variant(device_state.active_channel, ua.VariantType.Byte))
            
            status_node = await parent_node.get_child(f"{self.idx}:LastOperationStatus")
            await status_node.write_value(device_state.last_status)

            return [ua.Variant(device_state.last_status, ua.VariantType.String)]
        except Exception as e:
            logging.error(f"Error in SetChannel handler for {parent_name}: {e}")
            return [ua.Variant("SET_CHANNEL_FAILED", ua.VariantType.String)]

    @uamethod
    async def _reset_handler(self, parent):
        # This handler is now correct and safe
        parent_node = self.server.get_node(parent)
        parent_name = (await parent_node.read_browse_name()).Name
        try:
            address = int(parent_name.split('_')[1], 16)
            self.controller.reset_mux(address)
            device_state = self.controller.devices[address]
            channel_node = await parent_node.get_child(f"{self.idx}:ActiveChannel")
            await channel_node.write_value(ua.Variant(device_state.active_channel, ua.VariantType.Byte))
            status_node = await parent_node.get_child(f"{self.idx}:LastOperationStatus")
            await status_node.write_value(device_state.last_status)
            return [ua.Variant(device_state.last_status, ua.VariantType.String)]
        except Exception as e:
            return [ua.Variant("RESET_FAILED", ua.VariantType.String)]

    # Rescan handler is unchanged and correct
    @uamethod
    async def _rescan_handler(self, parent):
        # ... (code is unchanged)
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
        event_generator = await self.server.get_event_generator()
        event_generator.trigger(message="Address space updated after hardware rescan.")
        logging.info("Rescan complete.")