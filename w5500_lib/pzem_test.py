"""Test PZEM-004T on UART1 (GPIO 4=TX, GPIO 5=RX)"""
from machine import UART, Pin
import time

# PZEM-004T uses 9600 baud, Modbus RTU
UART_TX = 4
UART_RX = 5

print("PZEM-004T Test")
print(f"TX=GPIO{UART_TX}, RX=GPIO{UART_RX}")

uart = UART(1, baudrate=9600, tx=Pin(UART_TX), rx=Pin(UART_RX))
print("UART initialized")

# Try multiple addresses
addresses = [0x01, 0xF8]  # Default and broadcast

for addr in addresses:
    # Calculate CRC for command
    def crc16(data):
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    # Read Input Registers command
    cmd_data = bytes([addr, 0x04, 0x00, 0x00, 0x00, 0x0A])
    crc = crc16(cmd_data)
    cmd = cmd_data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    print(f"\nTrying address 0x{addr:02X}")
    print(f"Sending: {cmd.hex()}")

    # Clear buffer
    while uart.any():
        uart.read()

    uart.write(cmd)
    time.sleep_ms(500)  # Wait longer

    if uart.any():
        resp = uart.read()
        print(f"Response ({len(resp)} bytes): {resp.hex()}")

        if len(resp) >= 25:
            # Parse PZEM data
            voltage = (resp[3] << 8 | resp[4]) / 10.0  # V
            current = (resp[5] << 8 | resp[6] | resp[7] << 24 | resp[8] << 16) / 1000.0  # A
            power = (resp[9] << 8 | resp[10] | resp[11] << 24 | resp[12] << 16) / 10.0  # W
            energy = (resp[13] << 8 | resp[14] | resp[15] << 24 | resp[16] << 16)  # Wh
            freq = (resp[17] << 8 | resp[18]) / 10.0  # Hz
            pf = (resp[19] << 8 | resp[20]) / 100.0  # Power factor

            print(f"\n=== PZEM Data ===")
            print(f"Voltage: {voltage} V")
            print(f"Current: {current} A")
            print(f"Power: {power} W")
            print(f"Energy: {energy} Wh")
            print(f"Frequency: {freq} Hz")
            print(f"Power Factor: {pf}")
            break
    else:
        print("No response")

else:
    print("\nNo response from PZEM on any address!")
    print("Check:")
    print("1. PZEM TX (green/yellow) -> GPIO 5")
    print("2. PZEM RX (blue) -> GPIO 4")
    print("3. PZEM powered (5V + GND)")
