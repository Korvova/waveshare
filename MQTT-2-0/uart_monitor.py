"""Monitor UART RX/TX pins for any signal activity"""
from machine import Pin, UART
import time

# UART pins
TX_PIN = 4
RX_PIN = 5

print("=" * 40)
print("UART Signal Monitor")
print(f"TX = GPIO {TX_PIN}, RX = GPIO {RX_PIN}")
print("=" * 40)

# First, just read raw GPIO levels
tx = Pin(TX_PIN, Pin.IN)
rx = Pin(RX_PIN, Pin.IN)

print(f"\nRaw GPIO levels:")
print(f"  TX (GPIO {TX_PIN}): {tx.value()}")
print(f"  RX (GPIO {RX_PIN}): {rx.value()}")

# Monitor for changes
print("\nMonitoring for signal changes (10 seconds)...")
print("If PZEM is connected, we should see changes on RX")

last_tx = tx.value()
last_rx = rx.value()
tx_changes = 0
rx_changes = 0

start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < 10000:
    t = tx.value()
    r = rx.value()
    if t != last_tx:
        tx_changes += 1
        last_tx = t
    if r != last_rx:
        rx_changes += 1
        last_rx = r
    time.sleep_us(100)  # Sample fast

print(f"\nResults:")
print(f"  TX changes: {tx_changes}")
print(f"  RX changes: {rx_changes}")

if rx_changes == 0 and tx_changes == 0:
    print("\n[!] No activity detected!")
    print("    - Check if PZEM is powered (5V + GND)")
    print("    - Check wire connections")
elif rx_changes > 0:
    print("\n[OK] RX activity detected - PZEM may be responding")

# Now try UART and send command
print("\n" + "=" * 40)
print("Testing UART communication...")
print("=" * 40)

uart = UART(1, baudrate=9600, tx=Pin(TX_PIN), rx=Pin(RX_PIN))

# Clear any old data
while uart.any():
    uart.read()

# CRC16 for Modbus
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

# Send PZEM read command (address 0x01)
cmd_data = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A])
crc = crc16(cmd_data)
cmd = cmd_data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

print(f"Sending: {cmd.hex()}")
uart.write(cmd)

# Wait and check for response
time.sleep_ms(500)

if uart.any():
    resp = uart.read()
    print(f"Response: {resp.hex()}")
    print("[OK] Got response from PZEM!")
else:
    print("No UART response")

    # Check raw bytes on RX
    print("\nChecking raw data on RX pin...")
    raw_data = []
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < 2000:
        if uart.any():
            raw_data.append(uart.read(1))

    if raw_data:
        print(f"Raw data received: {b''.join(raw_data).hex()}")
    else:
        print("No raw data on RX")

print("\n" + "=" * 40)
print("Done")
