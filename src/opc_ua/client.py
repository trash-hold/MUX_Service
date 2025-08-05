import asyncio
from src.opc_ua.clientLogic import OpcUaClientLogic

class ClientCLI:
    """
    The Command-Line Interface for the OPC UA Client.
    This class handles user input and displays data, using OpcUaClientLogic
    to perform the actual work.
    """
    def __init__(self, logic: OpcUaClientLogic):
        self.logic = logic
        self.discovered_devices = []

    async def _show_menu(self):
        print("\n--- OPC UA Arduino Client ---")
        print("1. Discover MUX Devices")
        print("2. Show All Device States")
        print("3. Set MUX Channel")
        print("4. Reset a MUX")
        print("5. Trigger Hardware Rescan on Server")
        print("6. Exit")
        return input("Choose an option: ")

    async def run(self):
        """Main loop for the CLI application."""
        # Initial setup: find the gateway to enable other functions
        await self.logic.find_gateway_and_methods()
        
        while True:
            choice = await self._show_menu()
            if choice == '1':
                await self._handle_discover()
            elif choice == '2':
                await self._handle_show_states()
            elif choice == '3':
                await self._handle_set_channel()
            elif choice == '4':
                await self._handle_reset_mux()
            elif choice == '5':
                await self._handle_rescan()
            elif choice == '6':
                print("Exiting.")
                break
            else:
                print("Invalid option, please try again.")
            await asyncio.sleep(0.1) # a small sleep to prevent tight loop on error

    async def _handle_discover(self):
        print("\nDiscovering devices on the server...")
        self.discovered_devices = await self.logic.discover_devices()
        if not self.discovered_devices:
            print("No devices found.")
        else:
            print(f"Found {len(self.discovered_devices)} devices: {self.discovered_devices}")

    async def _handle_show_states(self):
        if not self.logic.device_nodes:
            print("\nNo devices discovered. Please run discovery (Option 1) first.")
            return
            
        print("\n--- Current Device States ---")
        print(f"{'Address':<10} | {'Active Channel':<15} | {'Last Status'}")
        print("-" * 45)
        
        for addr in sorted(self.logic.device_nodes.keys()):
            state = await self.logic.read_device_state(addr)
            if state:
                channel, status = state
                print(f"{addr:<10} | {channel:<15} | {status}")
            else:
                print(f"{addr:<10} | {'ERROR':<15} | {'Could not read state'}")
        print("-" * 45)

    async def _handle_set_channel(self):
        if not self.discovered_devices:
            print("\nPlease run discovery (Option 1) first.")
            return
        
        addr = input(f"Enter MUX address to control {self.discovered_devices}: ")
        if addr not in self.logic.device_nodes:
            print(f"Error: Invalid address '{addr}'.")
            return
            
        try:
            channel = int(input(f"Enter channel number (1-8) for MUX {addr}: "))
            if not (0 <= channel <= 255):
                raise ValueError("Channel out of range")
        except ValueError as e:
            print(f"Invalid channel number: {e}. Please enter an integer between 0 and 255.")
            return

        success = await self.logic.write_channel(addr, channel)
        if success:
            print(f"Successfully sent command to set MUX {addr} to channel {channel}.")
            print("Waiting a moment for status to update...")
            await asyncio.sleep(1) # Give server time to process and update status
            await self._handle_show_states()
        else:
            print(f"Failed to set channel for MUX {addr}.")

    async def _handle_reset_mux(self):
        if not self.discovered_devices:
            print("\nPlease run discovery (Option 1) first.")
            return
            
        addr = input(f"Enter MUX address to reset {self.discovered_devices}: ")
        if addr not in self.logic.device_nodes:
            print(f"Error: Invalid address '{addr}'.")
            return
            
        print(f"Sending reset command to MUX {addr}...")
        result = await self.logic.call_reset_mux(addr)
        print(f"Server method returned: '{result}'")
        await asyncio.sleep(1)
        await self._handle_show_states()

    async def _handle_rescan(self):
        print("\nRequesting server to perform a hardware rescan...")
        
        # The logic method now returns a success status
        success = await self.logic.call_rescan_hardware()
        
        if success:
            print("Server has completed the rescan. Run discovery (Option 1) again to see changes.")
            # Clear local cache as it's now potentially stale
            self.discovered_devices = []
            self.logic.device_nodes.clear()
        else:
            print("The rescan command failed or timed out. Please check the server logs.")