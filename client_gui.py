import sys
import asyncio
import qasync
import logging
from PySide6.QtWidgets import QApplication

# Assuming clientLogic.py is in the same directory or a reachable path
from src.opc_ua.clientLogic import OpcUaClientLogic
from src.common.utils import load_config_file
from src.gui.client_gui import OpcUaClientGui

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

CONFIG = './secret/opcua.json'

def main():
    """Main function to set up and run the application."""
    config = load_config_file(CONFIG)
    if not config:
        sys.exit(1)

    client = OpcUaClientLogic(config)

    app = QApplication(sys.argv)
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # The qasync event loop replaces the default asyncio loop
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    gui = OpcUaClientGui(client)
    gui.show()

    # Use a context manager to ensure the loop is cleaned up properly
    # and run the event loop until the application is closed.
    with event_loop:
        event_loop.run_forever()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Application shutdown.")