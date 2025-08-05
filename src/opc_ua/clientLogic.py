import asyncio
import logging
from asyncua import Client, ua, Node

class OpcUaClientLogic:
    def __init__(self, config: dict):
        self.client = Client(url=config['endpoint'], timeout=30) 
        self.namespace_uri = config['namespace_uri']
        node_map = config['nodes']
        self.gateway_name = node_map['gateway_object']
        self.mux_prefix = node_map['mux_prefix']
        self.channel_var_name = node_map['variables']['channel']
        self.status_var_name = node_map['variables']['status']
        self.rescan_method_name = node_map['methods']['rescan']
        self.reset_method_name = node_map['methods']['reset']
        # Get the new method name from config
        self.set_channel_method_name = node_map['methods']['set_channel']
        
        self.gateway_node = None
        self.rescan_method_node = None
        self.namespace_idx = 0
        # Cache now includes the set_channel method node
        self.device_nodes = {}

    async def connect(self):
        # This method is correct and unchanged
        logging.info(f"Attempting to connect to {self.client.server_url}...")
        try:
            await self.client.connect()
            self.namespace_idx = await self.client.get_namespace_index(self.namespace_uri)
            logging.info(f"Successfully connected. Namespace '{self.namespace_uri}' is at index {self.namespace_idx}.")
            return True
        except Exception as e:
            logging.error(f"Failed to connect or find namespace: {e}")
            try:
                server_namespaces = await self.client.get_namespace_array()
                logging.info("Available namespaces: %s", server_namespaces)
            except Exception:
                pass
            await self.client.disconnect()
            return False

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()

    async def find_gateway_and_methods(self):
        # This method is correct and unchanged
        try:
            objects_node = self.client.get_objects_node()
            self.gateway_node = await objects_node.get_child(f"{self.namespace_idx}:{self.gateway_name}")
            self.rescan_method_node = await self.gateway_node.get_child(f"{self.namespace_idx}:{self.rescan_method_name}")
        except Exception as e:
            logging.error(f"Error finding gateway node or methods: {e}")

    async def discover_devices(self) -> list[str]:
        if not self.gateway_node:
            return []
        self.device_nodes.clear()
        discovered_addrs = []
        try:
            for child_node in await self.gateway_node.get_children():
                browse_name = await child_node.read_browse_name()
                if browse_name.Name.startswith(self.mux_prefix):
                    addr_str = browse_name.Name.split('_')[1]
                    discovered_addrs.append(addr_str)
                    # --- Find and cache the new SetChannel method ---
                    self.device_nodes[addr_str] = {
                        'obj': child_node,
                        'channel': await child_node.get_child(f"{self.namespace_idx}:{self.channel_var_name}"),
                        'status': await child_node.get_child(f"{self.namespace_idx}:{self.status_var_name}"),
                        'reset': await child_node.get_child(f"{self.namespace_idx}:{self.reset_method_name}"),
                        'set_channel': await child_node.get_child(f"{self.namespace_idx}:{self.set_channel_method_name}")
                    }
            return sorted(discovered_addrs)
        except Exception as e:
            logging.error(f"An error occurred during device discovery: {e}")
            return []

    async def read_device_state(self, addr_str: str) -> tuple | None:
        # This method is correct and unchanged
        if addr_str not in self.device_nodes: return None
        try:
            nodes = self.device_nodes[addr_str]
            channel_val = await nodes['channel'].read_value()
            status_val = await nodes['status'].read_value()
            return channel_val, status_val
        except Exception as e:
            logging.error(f"Could not read state for device {addr_str}: {e}")
            return None

    # --- REWRITTEN: This now calls the method instead of writing to a variable ---
    async def write_channel(self, addr_str: str, channel: int) -> bool:
        """Calls the SetChannel method on the specified MUX object."""
        if addr_str not in self.device_nodes:
            return False
        try:
            mux_obj = self.device_nodes[addr_str]['obj']
            set_ch_method = self.device_nodes[addr_str]['set_channel']
            
            # Call the method with the channel as an argument
            result = await mux_obj.call_method(set_ch_method, ua.Variant(channel, ua.VariantType.Byte))
            logging.info(f"SetChannel for {addr_str} returned: {result}")
            return True
        except Exception as e:
            logging.error(f"Could not call SetChannel for device {addr_str}: {e}")
            return False

    # The other methods are correct and unchanged
    async def call_reset_mux(self, addr_str: str) -> str | None:
        if addr_str not in self.device_nodes: return None
        try:
            mux_obj = self.device_nodes[addr_str]['obj']
            reset_method = self.device_nodes[addr_str]['reset']
            result = await mux_obj.call_method(reset_method)
            return result
        except Exception as e:
            logging.error(f"Could not call Reset on device {addr_str}: {e}")
            return "CALL_FAILED"

    async def call_rescan_hardware(self):
        if not self.gateway_node or not self.rescan_method_node: return False
        try:
            await self.gateway_node.call_method(self.rescan_method_node)
            return True
        except Exception as e:
            logging.error(f"Failed to call RescanHardware: {e}")
            return False