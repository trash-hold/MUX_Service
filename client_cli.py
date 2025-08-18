# client_cli.py

import asyncio
import logging

from src.common.utils import load_config_file
from src.opc_ua.clientLogic import OpcUaClientLogic
from src.opc_ua.client import ClientCLI

CONFIG_PATH = './secret/opcua.json'

async def main():
    """
    Main entry point for the OPC UA CLI client.
    """
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger("asyncua").setLevel(logging.WARNING)

    # 1. Load Configuration
    config = load_config_file(CONFIG_PATH)
    if not config or 'endpoint' not in config or 'nodes' not in config:
        logging.critical("Configuration is missing 'endpoint' or 'nodes' section. Exiting.")
        return

    # 2. Instantiate the Core Logic
    client_logic = OpcUaClientLogic(config)

    try:
        # 3. *** KEY FIX: Connect to the Server ***
        # The connection must be established before running the CLI.
        # The endpoint URL from the config is used for the initial connection.
        if not await client_logic.connect(config['endpoint']):
            logging.error("Failed to connect to the OPC UA server. Please check the endpoint URL and server status.")
            return # Exit if connection fails

        # 4. Instantiate and Run the CLI Application
        cli_app = ClientCLI(client_logic)
        await cli_app.run()

    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Client shutting down due to user request.")
    except Exception as e:
        logging.error(f"An unexpected error occurred in the main application loop: {e}", exc_info=True)
    finally:
        # 5. Ensure disconnection when the application exits
        if client_logic.client:
            logging.info("Disconnecting client...")
            await client_logic.disconnect()
            logging.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")