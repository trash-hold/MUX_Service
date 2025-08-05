import asyncio
import logging

from src.common.utils import load_config_file
from src.opc_ua.clientLogic import OpcUaClientLogic
from src.opc_ua.client import ClientCLI

CONFIG_PATH = './secret/opcua.json'

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger("asyncua").setLevel(logging.WARNING)

    # 1. Load Configuration
    config = load_config_file(CONFIG_PATH)
    if not config or 'endpoint' not in config or 'nodes' not in config:
        logging.critical("Configuration is missing 'endpoint' or 'nodes' section. Exiting.")
        return

    # 2. Instantiate the Core Logic (pass the whole config dict)
    client_logic = OpcUaClientLogic(config)

    try:
        # 3. Connect to the Server
        if not await client_logic.connect():
            return # Exit if connection fails

        # 4. Instantiate and Run the CLI Application
        app = ClientCLI(client_logic)
        await app.run()

    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Client shutting down.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        # 5. Ensure disconnection
        logging.info("Disconnecting client...")
        await client_logic.disconnect()
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")