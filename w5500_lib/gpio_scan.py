"""Scan all GPIO pins"""
from machine import Pin

print("GPIO Scan (0-47):")
print("=" * 40)
for i in range(48):
    try:
        p = Pin(i, Pin.IN)
        v = p.value()
        print(f"GPIO {i:2d}: {v}")
    except Exception as e:
        print(f"GPIO {i:2d}: ERROR - {e}")
print("=" * 40)
