from machine import Pin
import dht
import time

print("DHT22 test on GPIO 42")
d = dht.DHT22(Pin(42))

for i in range(3):
    time.sleep(2)
    try:
        d.measure()
        print(f"Temp: {d.temperature()}C, Hum: {d.humidity()}%")
    except Exception as e:
        print(f"Error: {e}")
