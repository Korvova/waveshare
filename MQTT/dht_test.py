"""Test DHT22 sensor"""
from machine import Pin
import dht
import time

DHT_PIN = 41

print(f"Testing DHT22 on GPIO {DHT_PIN}")
print("=" * 40)

# Try both DHT22 and DHT11
for sensor_type in ["DHT22", "DHT11"]:
    print(f"\nTrying {sensor_type}...")
    if sensor_type == "DHT22":
        sensor = dht.DHT22(Pin(DHT_PIN))
    else:
        sensor = dht.DHT11(Pin(DHT_PIN))

    for attempt in range(5):
        time.sleep(2)  # DHT needs 2 sec between reads
        try:
            sensor.measure()
            t = sensor.temperature()
            h = sensor.humidity()
            print(f"  Attempt {attempt+1}: {t}°C, {h}%")
        except Exception as e:
            print(f"  Attempt {attempt+1}: Error - {e}")

print("\n" + "=" * 40)
print("Done")
