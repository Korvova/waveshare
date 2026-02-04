"""
Simple Web Server for Waveshare RP2350-POE-ETH-8DI-8RO
Using custom W5500 driver
"""
from machine import Pin, SoftSPI
from w5500_simple import W5500
import dht
import time

# ============= CONFIGURATION =============
# W5500 SPI pins
SPI_SCK  = 34
SPI_MOSI = 35
SPI_MISO = 36
SPI_CS   = 33
W5500_RST = 25

# Network
MAC = [0x00, 0x08, 0xDC, 0x12, 0x34, 0x56]
IP = [192, 168, 1, 100]
GW = [192, 168, 1, 1]
SN = [255, 255, 255, 0]

# Relay pins
RELAY_PINS = [17, 18, 19, 20, 21, 22, 23, 24]

# DHT22 sensor pin
DHT_PIN = 42

# ============= INIT =============
print("=" * 40)
print("RP2350 Web Server")
print("=" * 40)

# Relays
relays = [Pin(p, Pin.OUT, value=0) for p in RELAY_PINS]
print("Relays: all OFF")

# DHT22 sensor
dht_sensor = dht.DHT22(Pin(DHT_PIN))
print(f"DHT22 on pin {DHT_PIN}")

# SPI & W5500
cs = Pin(SPI_CS, Pin.OUT, value=1)
rst = Pin(W5500_RST, Pin.OUT)
spi = SoftSPI(baudrate=2000000, polarity=0, phase=0,
              sck=Pin(SPI_SCK), mosi=Pin(SPI_MOSI), miso=Pin(SPI_MISO))

w5500 = W5500(spi, cs, rst)
w5500.set_mac(MAC)
w5500.set_gateway(GW)
w5500.set_subnet(SN)
w5500.set_ip(IP)

# Wait for link
print("Waiting for link...", end="")
for _ in range(50):
    if w5500.get_link_status():
        print(" OK!")
        break
    print(".", end="")
    time.sleep_ms(100)
else:
    print(" TIMEOUT!")

ip = w5500.get_ip()
print(f"IP: {ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}")

# ============= WEB SERVER =============
def read_dht():
    """Read temperature and humidity from DHT22"""
    try:
        dht_sensor.measure()
        t = dht_sensor.temperature()
        h = dht_sensor.humidity()
        print(f"DHT: {t}C, {h}%")
        return t, h
    except Exception as e:
        print(f"DHT error: {e}")
        return None, None

def read_all_gpio():
    """Read all GPIO pins (0-47)"""
    values = []
    for i in range(48):
        try:
            p = Pin(i, Pin.IN)
            values.append(p.value())
        except:
            values.append(-1)
    return values

def html_page():
    temp, hum = read_dht()
    temp_str = f"{temp:.1f}" if temp else "--"
    hum_str = f"{hum:.1f}" if hum else "--"

    # Build body first
    body = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'><title>RP2350</title>
<meta http-equiv='refresh' content='10'>
<style>body{{font-family:Arial;margin:20px}}
.sensor{{background:#2196F3;color:#fff;padding:20px;border-radius:10px;margin:10px 0;font-size:20px}}
.r{{margin:8px;padding:8px;background:#eee;border-radius:5px}}
.on{{background:#4CAF50;color:#fff;padding:6px 12px;border:none;cursor:pointer}}
.off{{background:#f44336;color:#fff;padding:6px 12px;border:none;cursor:pointer}}
</style></head><body><h1>RP2350 Control</h1>
<div class='sensor'>Temp: <b>{temp_str} C</b> | Humidity: <b>{hum_str}%</b></div>
<h2>Relays</h2>"""

    for i in range(8):
        st = "ON" if relays[i].value() else "OFF"
        body += f"<div class='r'>Relay {i+1}: <b>{st}</b> "
        body += f"<a href='/r?n={i+1}&s=1'><button class='on'>ON</button></a> "
        body += f"<a href='/r?n={i+1}&s=0'><button class='off'>OFF</button></a></div>"

    body += "<hr><a href='/a?s=1'><button class='on'>ALL ON</button></a> "
    body += "<a href='/a?s=0'><button class='off'>ALL OFF</button></a>"

    # GPIO status - disabled (causes socket timeout)
    # body += "<h2>GPIO</h2><pre>...</pre>"
    body += "</body></html>"

    # Build headers with Content-Length
    body_bytes = body.encode()
    headers = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body_bytes)}\r\nConnection: close\r\n\r\n"
    return headers.encode() + body_bytes

def handle_request(req):
    """Parse request and return response"""
    if b'GET /r?' in req:
        try:
            s = req.decode()
            n = int(s.split('n=')[1].split('&')[0])
            v = int(s.split('s=')[1].split(' ')[0].split('&')[0])
            if 1 <= n <= 8:
                relays[n-1].value(v)
                print(f"Relay {n} -> {'ON' if v else 'OFF'}")
        except: pass
        return b"HTTP/1.1 302 Found\r\nLocation: /\r\n\r\n"

    elif b'GET /a?' in req:
        try:
            s = req.decode()
            v = int(s.split('s=')[1].split(' ')[0])
            for r in relays:
                r.value(v)
            print(f"ALL -> {'ON' if v else 'OFF'}")
        except: pass
        return b"HTTP/1.1 302 Found\r\nLocation: /\r\n\r\n"

    elif b'GET / ' in req:
        return html_page()

    return b"HTTP/1.1 404 Not Found\r\n\r\n404"

# Main loop
SOCK = 0
print(f"\nStarting server on http://{ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}:80")
print("=" * 40)

idle_count = 0
link_check = 0

while True:
    try:
        # Check link every 100 iterations
        link_check += 1
        if link_check >= 100:
            link_check = 0
            if not w5500.get_link_status():
                print("Link lost! Waiting...")
                w5500.socket_close(SOCK)
                while not w5500.get_link_status():
                    time.sleep_ms(500)
                print("Link restored!")
                idle_count = 0
                continue

        status = w5500.socket_status(SOCK)

        if status == W5500.SOCK_CLOSED:
            if w5500.socket_open(SOCK, 80):
                print("Socket opened")
                idle_count = 0

        elif status == W5500.SOCK_INIT:
            if w5500.socket_listen(SOCK):
                print("Listening on :80...")

        elif status == W5500.SOCK_LISTEN_STATUS:
            idle_count += 1
            # If stuck listening too long, reset socket
            if idle_count > 500:
                print("Idle timeout, resetting...")
                w5500.socket_close(SOCK)
                idle_count = 0
            time.sleep_ms(20)

        elif status == W5500.SOCK_ESTABLISHED:
            idle_count = 0
            # Wait a bit for data
            time.sleep_ms(50)
            avail = w5500.socket_recv_available(SOCK)
            if avail > 0:
                req = w5500.socket_recv(SOCK, min(avail, 512))
                print(f"Request: {len(req)} bytes")
                try:
                    print("Building response...")
                    resp = handle_request(req)
                    print(f"Response: {len(resp)} bytes")
                    w5500.socket_send(SOCK, resp)
                    time.sleep_ms(50)
                    print("Sent")
                except Exception as e:
                    print(f"Handler error: {e}")
            # Disconnect and close
            w5500.socket_disconnect(SOCK)
            time.sleep_ms(50)
            w5500.socket_close(SOCK)
            time.sleep_ms(50)

        elif status == W5500.SOCK_CLOSE_WAIT:
            w5500.socket_disconnect(SOCK)
            time.sleep_ms(10)

        else:
            # Unknown status - close and reopen
            print(f"Unknown status {status}, resetting...")
            w5500.socket_close(SOCK)
            time.sleep_ms(100)

    except Exception as e:
        print(f"Error: {e}")
        try:
            w5500.socket_close(SOCK)
        except:
            pass
        time.sleep_ms(500)
