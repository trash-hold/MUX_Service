import json
import logging
from src.communicator.abstractInterface import CommunicationInterface
from src.communicator.serial_communicator import SerialCommunicator

def load_config_file(filepath: str) -> dict | None:
    """
    Loads a specified JSON config file.

    Args:
        filepath (str): The path to the JSON file.

    Returns:
        A dictionary with the configuration, or None if an error occurs.
    """
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON from {filepath}: {e}")
        return None

def create_communicator(hw_config: dict) -> CommunicationInterface | None:
    """
    Factory function to create the correct communicator object based on the
    hardware configuration dictionary. This allows for easy extension to
    other communication types in the future (e.g., Ethernet).

    Args:
        hw_config (dict): The parsed hardware configuration from hardware_config.json.

    Returns:
        An object that implements the CommunicationInterface, or None on failure.
    """
    comm_type = hw_config.get("communication_type")
    settings = hw_config.get("settings")

    if not comm_type or not settings:
        logging.error("Hardware config must include 'communication_type' and 'settings' keys.")
        return None

    # --- Serial Communication ---
    if comm_type == "serial":
        port = settings.get("port")
        if not port:
            logging.error("Serial settings must include a 'port'.")
            return None
        
        communicator = SerialCommunicator(
            port=port,
            baudrate=settings.get("baudrate", 115200) # Use 115200 as a default
        )
        logging.info(f"Created SERIAL communicator for port {port}")
        return communicator