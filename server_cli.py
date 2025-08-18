import logging
import asyncio
import contextlib

from src.opc_ua.serverLogic import OpcUaServer 
from src.communicator.deviceCommincator import DeviceController
from src.common.utils import load_config_file, create_communicator

HARDWARE_CONFIG = './secret/config.json'
SERVER_CONFIG = './secret/opcua.json'

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    
    controller = None
    server = None
    main_task = None

    try:
        logging.info("Loading configurations...")
        hw_config = load_config_file(HARDWARE_CONFIG)
        server_config = load_config_file(SERVER_CONFIG)
        if not hw_config or not server_config:
            raise RuntimeError("Failed to load configuration.")

        communicator = create_communicator(hw_config)
        if not communicator:
            raise RuntimeError("Failed to create communicator from config.")

        controller = DeviceController(communicator)
        server = OpcUaServer(controller, server_config)

        logging.info("Attempting initial connection to device...")
        if not controller.connect():
            logging.warning("Failed to connect to device on startup. Will attempt to reconnect in the background.")
        else:
            logging.info("Device connected successfully.")

        await server.start()
        
        # Keep the main task alive to handle shutdown signals
        main_task = asyncio.Future()
        await main_task

    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Shutdown signal received.")
    except Exception as e:
        logging.critical(f"An unhandled exception occurred: {e}", exc_info=True)
    finally:
        logging.info("Starting graceful shutdown...")
        if main_task and not main_task.done():
            main_task.set_result(True)
        
        if server:
            logging.info("Stopping OPC UA server...")
            await server.stop() 
        
        if controller:
            logging.info("Stopping communicator...")
            controller.disconnect()
            
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())