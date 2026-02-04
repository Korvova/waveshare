"""Scan ALL GPIO pins to find UART activity from PZEM"""
from machine import Pin
import time

print("=" * 40)
print("Scanning ALL GPIO for UART activity")
print("=" * 40)

# Skip known used pins
SKIP_PINS = [
    # W5500 Ethernet
    33, 34, 35, 36, 25,
    # Relays
    17, 18, 19, 20, 21, 22, 23, 24,
    # Digital inputs
    9, 10, 11, 12, 13, 14, 15, 16,
    # DHT22
    42,
]

# First read all GPIO levels
print("\nReading all GPIO levels...")
levels = {}
for i in range(48):
    try:
        p = Pin(i, Pin.IN)
        levels[i] = p.value()
    except:
        levels[i] = None

print("\nGPIO levels (0-47):")
for i in range(48):
    if levels[i] is not None:
        skip = " (SKIP)" if i in SKIP_PINS else ""
        print(f"  GPIO {i:2d}: {levels[i]}{skip}")

# Now monitor for changes on all available pins
print("\n" + "=" * 40)
print("Monitoring for signal changes (15 sec)...")
print("Connect PZEM and watch for activity")
print("=" * 40)

pins = {}
changes = {}
last_val = {}

for i in range(48):
    if i not in SKIP_PINS and levels[i] is not None:
        try:
            pins[i] = Pin(i, Pin.IN)
            last_val[i] = pins[i].value()
            changes[i] = 0
        except:
            pass

start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < 15000:
    for i, p in pins.items():
        v = p.value()
        if v != last_val[i]:
            changes[i] += 1
            last_val[i] = v
    time.sleep_us(50)

print("\nResults - GPIO with signal changes:")
found = False
for i in sorted(changes.keys()):
    if changes[i] > 0:
        found = True
        print(f"  GPIO {i}: {changes[i]} changes")

if not found:
    print("  No changes detected on any GPIO!")
    print("\n  Check:")
    print("  1. Is PZEM powered? (5V LED on?)")
    print("  2. Are TXD/RXD wires connected?")
else:
    print("\n  Try using these GPIO pins for UART!")

# Also try all possible UART pin combinations
print("\n" + "=" * 40)
print("Testing UART on GPIO 0-8 (common pins)")
print("=" * 40)

from machine import UART

# Try different pin combinations
test_pins = [
    (0, 1),
    (4, 5),
    (8, 9),
    (0, 5),
    (4, 1),
]

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

cmd_data = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A])
crc = crc16(cmd_data)
cmd = cmd_data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

for tx, rx in test_pins:
    try:
        print(f"\nTrying TX=GPIO{tx}, RX=GPIO{rx}...")
        uart = UART(1, baudrate=9600, tx=Pin(tx), rx=Pin(rx))

        # Clear buffer
        while uart.any():
            uart.read()

        uart.write(cmd)
        time.sleep_ms(300)

        if uart.any():
            resp = uart.read()
            print(f"  RESPONSE: {resp.hex()}")
            print(f"  [!!!] FOUND PZEM on TX={tx}, RX={rx}")
        else:
            print(f"  No response")

    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "=" * 40)
print("Done")
