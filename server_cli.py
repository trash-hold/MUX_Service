import logging
import asyncio 

from src.opc_ua.serverLogic import OpcUaServer 
from src.communicator.deviceCommincator import DeviceController
from src.common.utils import load_config_file, create_communicator

HARDWARE_CONFIG = './secret/config.json'
SERVER_CONFIG = './secret/opcua.json'

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    
    # Initialize components to None for robust cleanup in the 'finally' block
    controller = None
    server = None

    try:
        # --- 1. CONFIGURATION AND SETUP ---
        logging.info("Loading configurations...")
        hw_config = load_config_file(HARDWARE_CONFIG)
        server_config = load_config_file(SERVER_CONFIG)
        if not hw_config or not server_config:
            logging.critical("Failed to load configuration. Exiting.")
            return

        communicator = create_communicator(hw_config)
        if not communicator:
            logging.critical("Failed to create communicator from config. Exiting.")
            return

        controller = DeviceController(communicator)
        server = OpcUaServer(controller, server_config)

        # --- 2. STARTUP ---
        logging.info("Starting communication with device...")
        if not controller.connect():
            logging.critical("Failed to start communication with device. Exiting.")
            return

        logging.info("Starting OPC UA server and populating nodes...")
        # The server.start() will now do its initial scan and population
        await server.start()
        logging.info("Server startup complete. Running indefinitely...")

        # --- 3. RUN INDEFINITELY (THE CRITICAL FIX) ---
        # This loop keeps the main coroutine alive, preventing the program
        # from exiting prematurely. The service will now run forever until
        # it's interrupted by Ctrl+C.
        while True:
            await asyncio.sleep(1)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Shutdown signal received.")

    finally:
        # --- 4. GRACEFUL SHUTDOWN ---
        # This block now runs only after the 'while' loop is broken by an exception.
        logging.info("Starting graceful shutdown...")
        
        # Shut down in reverse order of startup
        if server:
            # It's crucial that your OpcUaServer has a stop() method
            # to gracefully shut down the asyncua server.
            logging.info("Stopping OPC UA server...")
            await server.stop() 
        
        if controller:
            logging.info("Stopping communicator...")
            controller.disconnect()
            
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    # The try/except here is good, but the main one is inside the async function
    asyncio.run(main())