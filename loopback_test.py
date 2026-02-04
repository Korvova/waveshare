"""Loopback test - connect TX to RX on USB-TTL adapter"""
import serial
import sys

port = sys.argv[1] if len(sys.argv) > 1 else 'COM8'

print(f"Loopback test on {port}")
print("Make sure TX and RX are connected together!")
print()

ser = serial.Serial(port, 9600, timeout=1)

# Send test data
test = b'HELLO_PZEM_TEST'
print(f"Sending: {test}")
ser.write(test)

import time
time.sleep(0.2)

if ser.in_waiting:
    resp = ser.read(ser.in_waiting)
    print(f"Received: {resp}")
    if resp == test:
        print("\n[OK] USB-TTL adapter works!")
    else:
        print("\n[?] Partial data received")
else:
    print("\n[FAIL] No data received!")
    print("USB-TTL adapter may be broken or TX/RX not connected")

ser.close()
