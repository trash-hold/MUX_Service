from src.communicator.serial_communicator import SerialCommunicator

if __name__ == "__main__":
    available_ports = SerialCommunicator.list_available_ports()
    if not available_ports:
        exit()

    # --- Setup ---
    # port_name = input("Enter the COM port to use: ")
    port_name = "COM3" # For development, hardcode your port
    communicator = SerialCommunicator(port=port_name, baudrate=115200)
    
    if not communicator.start():
        print("Exiting program.")
        exit()

    print("\n--- Interactive Console ---")
    print("Commands: set <addr> <ch> | reset <addr> | scan | test | exit")

    try:
        while True:
            user_input = input("> ").strip().lower()
            parts = user_input.split()
            command = parts[0]

            if command == "exit":
                break
            elif command == "test":
                result = communicator.test_connection()
                print(f"Response: {result}")
            elif command == "reset" and len(parts) == 2:
                try:
                    addr = int(parts[1])
                    status = communicator.reset_mux(addr)
                    print(f"Status: {status.name}")
                except ValueError:
                    print("Error: Address must be an integer.")
            elif command == "set" and len(parts) == 3:
                try:
                    addr = int(parts[1])
                    ch = int(parts[2])
                    status = communicator.set_channel(addr, ch)
                    print(f"Status: {status.name}")
                except ValueError:
                    print("Error: Address and channel must be integers.")
            elif command == "scan":
                print("Scanning for I2C devices...")
                devices = communicator.scan_i2c_bus()
                if devices is not None:
                    print(f"Found {len(devices)} devices at addresses: {[hex(d) for d in devices]}")
                else:
                    print("Scan failed.")
            else:
                print("Unknown command. Use: set, reset, scan, test, exit")

    except KeyboardInterrupt:
        print("\nUser interrupted. Shutting down.")
    finally:
        communicator.stop()
        print("Program finished.")