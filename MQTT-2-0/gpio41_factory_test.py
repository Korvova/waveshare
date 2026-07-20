from machine import Pin
import time

TEST_PIN = 41
DELAY_MS = 1000

p = Pin(TEST_PIN, Pin.OUT)

print("GPIO%d factory voltage test" % TEST_PIN)
print("Measure GPIO%d to GND: voltage should switch 0V / 3.3V every second." % TEST_PIN)

while True:
    p.value(0)
    print("GPIO%d = 0" % TEST_PIN)
    time.sleep_ms(DELAY_MS)

    p.value(1)
    print("GPIO%d = 1" % TEST_PIN)
    time.sleep_ms(DELAY_MS)
