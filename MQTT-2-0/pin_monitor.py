"""Monitor GPIO pin values"""
from machine import Pin
import time

PIN = 42

p = Pin(PIN, Pin.IN)
print(f"Monitoring GPIO {PIN}...")
print("Press Ctrl+C to stop")
print()

last = -1
count = 0
for i in range(100):
    v = p.value()
    if v != last:
        print(f"[{i:3d}] GPIO {PIN} = {v}")
        last = v
        count += 1
    time.sleep_ms(50)

print(f"\nTotal changes: {count}")
print(f"Final value: {p.value()}")
