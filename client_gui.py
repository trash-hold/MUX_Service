
import sys
import argparse
import logging
from PySide6.QtWidgets import (
    QApplication, QMessageBox
)

from src.common.utils import load_config_file, create_communicator
from src.communicator.deviceCommincator import DeviceController
from src.opc_ua.client import GUIClient

def main():
    parser = argparse.ArgumentParser(description="GUI Client for MUX Controller.")
    parser.add_argument("--config", required=True, help="Path to the hardware config JSON file.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    app = QApplication(sys.argv)

    hw_config = load_config_file(args.config)
    if not hw_config: sys.exit(1)

    communicator = create_communicator(hw_config)
    if not communicator: sys.exit(1)

    controller = DeviceController(communicator)
    if not controller.connect():
        QMessageBox.critical(None, "Connection Error", "Could not connect to hardware. The application will close.")
        sys.exit(1)
    
    window = GUIClient(controller)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()