#include "Wire.h"

// Constants
#define BAUDRATE 115200     // Serial baudrate
#define BOT_ADR 0x20        // Lowest available address of MUX boards
#define TOP_ADR 0x27        // Top most address of MUX board
#define MAX_I2C_DEVICES 16  // Max amount of addresses that will be sent in one transmision

struct Com {
  static constexpr const char* SET   = "SET";
  static constexpr const char* RESET = "RST";
  static constexpr const char* TEST  = "TST";
  static constexpr const char* SCAN  = "SCN";
}Commands;

enum ErrorCodes{ 
  SUCCESS = 0x00, 
  COM_ERROR = 0x01,
  ADDR_ERROR = 0x02
};

// Global variables
String command="";
word inputs=0x00;

// Function declarations
ErrorCodes resetMUX(const byte& addr);
ErrorCodes setOutput(const word& dataA, const word& dataB, const byte& addr=0x20);
ErrorCodes sendByte(const word& data, const word& reg, const byte& addr=0x20);

// ================================================================================
// Main 
// ================================================================================
void setup() {
  /*
  * Opens Serial port @ BAUDRATE and initializes the MUX
  */
  Serial.begin(BAUDRATE);
  Wire.begin();     // I2C start
  for (byte i=BOT_ADR; i<=TOP_ADR; ++i)
    // Reset all channels before start 
    resetMUX(i);
}

void loop() {
  if (Serial.available()) {

    command = Serial.readStringUntil(' ');
    command.toUpperCase();

    if ( command.startsWith( Commands.RESET ) )  //RST addr
    {

      String addr_str = Serial.readStringUntil(' ');
      byte address = addr_str.toInt();
      if ( address >= BOT_ADR && address <= TOP_ADR )
      {
        ErrorCodes status = resetMUX(address);
        Serial.println( (uint8_t) status);
      }
      else
        // Address out of scope
        Serial.println( (uint8_t) ADDR_ERROR);
    }

    else if ( command.startsWith( Commands.SET) )  //SET addr ch
    {
      String addr_str = Serial.readStringUntil(' ');
      byte address = addr_str.toInt();

      String ch_str = Serial.readStringUntil(' ');
      byte channel = ch_str.toInt();

      if ( address >= BOT_ADR && address <= TOP_ADR && channel >= 1 && channel <=8 )
      {
        byte output = 0x00;
        // Pick only one channel and turn off the rest
        bitSet(output, channel-1);
        ErrorCodes status = setOutput( ~output, output, address );
        Serial.println( (uint8_t) status);
      }
      else
        // Inputs out of range 
        Serial.println( (uint8_t) ADDR_ERROR );
    }

    else if ( command.startsWith( Commands.SCAN ) )
      {
        scan();
      }

    else if (command.startsWith( Commands.TEST ))
    {
        Serial.println("TBI");
    }
  }
  delay(100);
}


// ================================================================================
// Function definitions
// ================================================================================
ErrorCodes resetMUX(const byte& addr)
{
  /*
  * Resets MUX board under given I2C address (all channels set to 0)
  */

  // Bank A
  Wire.beginTransmission(addr);
  Wire.write(0x00); // IODIRA register
  Wire.write(0x00); // set all of bank A to outputs
  uint8_t status = Wire.endTransmission();

  if(status != 0x00)
    return COM_ERROR;

  // Bank B
  Wire.beginTransmission(addr);
  Wire.write(0x01); // IODIRB register
  Wire.write(0x00); // set all of bank B to outputs
  status = Wire.endTransmission();

  if(status != 0x00)
    return COM_ERROR;

  // Reset
  return setOutput(0, 0, addr);  //set all outputs to 0x00
}

ErrorCodes sendByte(const word& data, const word& reg, const byte& addr)
{
  /*
  * Writes word into MUX register 
  * addr -- the MUX I2C address
  * reg -- the MUX register
  */
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(data);
  uint8_t status = Wire.endTransmission();

  return status == 0x00 ? SUCCESS : COM_ERROR;
}

ErrorCodes setOutput(const word& dataA, const word& dataB, const byte& addr)
{
  /*
  * Turns on channels on MUX board with given I2C address
  * dataA -- byte that sets mode for Bank A outputs (each bit = state of channel, 1 = ON)
  * dataB -- byte that sets mode for Bank B outputs (each bit = state of channel, 1 = ON)
  */
  ErrorCodes status = sendByte( dataA, 0x12, addr );  // GPIOA
  if (status != SUCCESS)
    return status;

  status = sendByte( dataB, 0x13, addr );  // GPIOB
  return status;
}

void scan()
{
  byte error, address;

  uint8_t nDevices;
  byte addresses[MAX_I2C_DEVICES];

  nDevices = 0;
  for(address = 1; address < 127; address++ )
  {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    if (error == 0)
    {
      // Check if buffer is not full
      if (nDevices >= MAX_I2C_DEVICES)
      {
          // Inform the receiver how many addresses will be transfered 
          Serial.print(MAX_I2C_DEVICES);
          // Inform that this is not the end of the tranmission
          Serial.print(0x00);

          // Send all the addresses that were acquired
          for(uint8_t i = 0; i < MAX_I2C_DEVICES; i++)
          {
            Serial.print(addresses[i]);
            // Zero them so they won't be sent twice
            addresses[i] = 0x00;
          }

          // Restart count
          nDevices = 0;
      }

      // Add new address to the list
      addresses[nDevices] = address;
      nDevices++;
      
    }

  }

  // Inform the receiver how many addresses will be transfered 
  Serial.print(nDevices);
  // Inform that this is the end of the tranmission
  Serial.print(0xFF);

  // Send all the addresses that were acquired
  for(uint8_t i = 0; i < nDevices; i++)
  {
    Serial.print(addresses[i]);
  } 
  
}
