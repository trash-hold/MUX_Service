import asyncio
import logging
from asyncua import Client, ua, Node

class OpcUaClientLogic:
    def __init__(self, config: dict):
        self.client = Client(url=config['endpoint'], timeout=10)
        self.namespace_uri = config['namespace_uri']
        
        # --- REWORK: Map new variable names from config ---
        node_map = config['nodes']
        self.gateway_name = node_map['gateway_object']
        self.mux_prefix = node_map['mux_prefix']
        
        # Variable names
        var_names = node_map['variables']
        self.channel_var_name = var_names['channel']
        self.status_var_name = var_names['status']
        self.set_channel_var_name = var_names['set_channel'] # Was a method
        self.reset_var_name = var_names['reset']             # Was a method
        self.mux_count_var_name = var_names['mux_count']     # New variable
        
        # Method names
        self.rescan_method_name = node_map['methods']['rescan']
        
        # Internal state
        self.gateway_node: Node | None = None
        self.rescan_method_node: Node | None = None
        self.mux_count_node: Node | None = None # New node cache
        self.namespace_idx = 0
        self.device_nodes = {} # Cache for MUX device nodes

    async def connect(self, new_url: str):
        """Creates a new client instance and attempts to connect."""
        self.client = Client(url=new_url, timeout=10)
        logging.info(f"Attempting to connect to {new_url}...")
        try:
            await self.client.connect()
            logging.info("STEP 1/3: Physical connection successful.")
            self.namespace_idx = await self.client.get_namespace_index(self.namespace_uri)
            logging.info(f"STEP 2/3: Namespace '{self.namespace_uri}' found at index {self.namespace_idx}.")
            logging.info("STEP 3/3: Base connection process complete.")
            return True
        except Exception as e:
            logging.error(f"CONNECTION FAILED: An error occurred: {e}", exc_info=False)
            self.client = None
            return False

    async def disconnect(self):
        if self.client and self.client.uaclient:
            try:
                await self.client.disconnect()
                logging.info("Disconnected from server.")
            except Exception as e:
                logging.warning(f"Error during disconnect, but proceeding: {e}")
        self.client = None
        self.gateway_node = None
        self.rescan_method_node = None
        self.mux_count_node = None
        self.device_nodes.clear()
        self.namespace_idx = 0

    async def find_gateway_and_methods(self):
        """Finds the main gateway object and its children (methods and variables)."""
        try:
            objects_node = self.client.get_objects_node()
            self.gateway_node = await objects_node.get_child(f"{self.namespace_idx}:{self.gateway_name}")
            
            # --- REWORK: Find the rescan method AND the new mux count variable ---
            self.rescan_method_node = await self.gateway_node.get_child(f"{self.namespace_idx}:{self.rescan_method_name}")
            self.mux_count_node = await self.gateway_node.get_child(f"{self.namespace_idx}:{self.mux_count_var_name}")
            logging.info("Successfully found Gateway object and its key members.")
        except Exception as e:
            logging.error(f"Error finding gateway node or its members: {e}")

    async def discover_devices(self) -> list[str]:
        """Discovers MUX objects under the gateway and caches their variable nodes."""
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
                    
                    # --- REWORK: Cache the variable nodes, not methods ---
                    self.device_nodes[addr_str] = {
                        'obj': child_node,
                        'channel_val': await child_node.get_child(f"{self.namespace_idx}:{self.channel_var_name}"),
                        'status_val': await child_node.get_child(f"{self.namespace_idx}:{self.status_var_name}"),
                        'set_channel_var': await child_node.get_child(f"{self.namespace_idx}:{self.set_channel_var_name}"),
                        'reset_var': await child_node.get_child(f"{self.namespace_idx}:{self.reset_var_name}"),
                    }
            return sorted(discovered_addrs)
        except Exception as e:
            logging.error(f"An error occurred during device discovery: {e}")
            return []

    async def read_device_state(self, addr_str: str) -> tuple | None:
        if addr_str not in self.device_nodes: return None
        try:
            nodes = self.device_nodes[addr_str]
            channel_val = await nodes['channel_val'].read_value()
            status_val = await nodes['status_val'].read_value()
            return channel_val, status_val
        except Exception as e:
            logging.error(f"Could not read state for device {addr_str}: {e}")
            return None

    # --- NEW METHOD ---
    async def read_mux_count(self) -> int | None:
        """Reads the value of the MuxBoardCount variable."""
        if not self.mux_count_node: return None
        try:
            count = await self.mux_count_node.read_value()
            return count
        except Exception as e:
            logging.error(f"Could not read Mux board count: {e}")
            return None

    # --- REWORKED: This now writes to a variable ---
    async def write_channel(self, addr_str: str, channel: int) -> bool:
        """Writes a new value to the SetChannel variable on the specified MUX object."""
        if addr_str not in self.device_nodes:
            return False
        try:
            set_ch_var_node = self.device_nodes[addr_str]['set_channel_var']
            await set_ch_var_node.write_value(ua.Variant(channel, ua.VariantType.Byte))
            logging.info(f"Successfully wrote {channel} to SetChannel for MUX {addr_str}")
            return True
        except Exception as e:
            logging.error(f"Could not write to SetChannel for device {addr_str}: {e}")
            return False

    # --- REWORKED: Renamed and now writes to a variable ---
    async def trigger_reset_mux(self, addr_str: str) -> bool:
        """Writes 'True' to the Reset variable to trigger a reset on the MUX."""
        if addr_str not in self.device_nodes: return False
        try:
            reset_var_node = self.device_nodes[addr_str]['reset_var']
            await reset_var_node.write_value(True)
            logging.info(f"Successfully wrote True to Reset for MUX {addr_str}")
            return True
        except Exception as e:
            logging.error(f"Could not write to Reset for device {addr_str}: {e}")
            return False

    async def call_rescan_hardware(self):
        # This method remains unchanged as rescan is still a method.
        if not self.gateway_node or not self.rescan_method_node: return False
        try:
            await self.gateway_node.call_method(self.rescan_method_node)
            return True
        except Exception as e:
            logging.error(f"Failed to call RescanHardware: {e}")
            return False