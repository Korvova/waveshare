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

# Digital inputs (door sensor on D1)
DI1_PIN = 9  # Door sensor

# ============= LOGGING =============
LOG_SIZE = 20  # Keep last 20 entries
logs = []

def log(msg):
    """Add log entry with timestamp"""
    global logs
    t = time.ticks_ms()
    entry = f"[{t}] {msg}"
    print(entry)
    logs.append(entry)
    if len(logs) > LOG_SIZE:
        logs.pop(0)

# ============= PULSE TIMER =============
# Non-blocking pulse: store (relay_index, end_time, restore_value)
pulse_tasks = []

def check_pulses():
    """Check and complete any pending pulse tasks"""
    global pulse_tasks
    now = time.ticks_ms()
    completed = []
    for i, (relay_idx, end_time, restore_val) in enumerate(pulse_tasks):
        if time.ticks_diff(now, end_time) >= 0:
            relays[relay_idx].value(restore_val)
            actual = relays[relay_idx].value()
            log(f"R{relay_idx+1} pulse done, restored={restore_val} actual={actual}")
            completed.append(i)
    # Remove completed (in reverse to keep indices valid)
    for i in reversed(completed):
        pulse_tasks.pop(i)

# ============= INIT =============
log("=" * 30)
log("RP2350 Web Server")
log("=" * 30)

# Relays
relays = [Pin(p, Pin.OUT, value=0) for p in RELAY_PINS]
print("Relays: all OFF")

# DHT22 sensor
dht_sensor = dht.DHT22(Pin(DHT_PIN))
print(f"DHT22 on pin {DHT_PIN}")

# Door sensor (D1)
door_pin = Pin(DI1_PIN, Pin.IN, Pin.PULL_UP)
print(f"Door sensor on D1 (GPIO {DI1_PIN})")
last_door_state = door_pin.value()

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
# Last DHT reading cache
dht_cache = (None, None)
dht_last_read = 0

def read_dht():
    """Read temperature and humidity from DHT22 (cached, every 30s)"""
    global dht_cache, dht_last_read
    now = time.ticks_ms()
    # Only read every 30 seconds
    if time.ticks_diff(now, dht_last_read) < 30000 and dht_cache[0] is not None:
        return dht_cache
    try:
        dht_sensor.measure()
        dht_cache = (dht_sensor.temperature(), dht_sensor.humidity())
        dht_last_read = now
        log(f"DHT: {dht_cache[0]}C, {dht_cache[1]}%")
        return dht_cache
    except:
        return dht_cache  # Return old value on error

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
    # Door sensor: 0=open, 1=closed (inverted)
    door_val = door_pin.value()
    door_str = "🔒 ДВЕРЬ ЗАКРЫТА" if door_val else "🔓 ДВЕРЬ ОТКРЫТА"
    door_color = "#f44336" if door_val else "#4CAF50"  # red=closed, green=open

    # Build body first (no auto-refresh, use AJAX)
    body = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'><title>RP2350</title>
<style>body{{font-family:Arial;margin:20px}}
.sensor{{background:#2196F3;color:#fff;padding:20px;border-radius:10px;margin:10px 0;font-size:20px}}
.r{{margin:8px;padding:8px;background:#eee;border-radius:5px}}
.on{{background:#4CAF50;color:#fff;padding:6px 12px;border:none;cursor:pointer}}
.off{{background:#f44336;color:#fff;padding:6px 12px;border:none;cursor:pointer}}
.pulse{{background:#FF9800;color:#fff;padding:6px 12px;border:none;cursor:pointer}}
.pulsing{{background:#E91E63;animation:blink 0.5s infinite}}
@keyframes blink{{50%{{opacity:0.5}}}}
</style>
<script>
function pulse(n,btn){{
btn.className='pulsing';btn.innerText='WAIT...';
fetch('/p?n='+n).then(()=>setTimeout(upd,5100));
}}
function upd(){{
fetch('/api').then(r=>r.json()).then(d=>{{
document.getElementById('temp').innerText=d.t||'--';
document.getElementById('hum').innerText=d.h||'--';
for(var i=0;i<8;i++)document.getElementById('s'+i).innerText=d.r[i]?'ON':'OFF';
var de=document.getElementById('door');
de.innerText=d.d?'🔒 ДВЕРЬ ЗАКРЫТА':'🔓 ДВЕРЬ ОТКРЫТА';
de.parentElement.style.background=d.d?'#f44336':'#4CAF50';
}}).catch(()=>{{}});
}}
setInterval(upd,2000);
</script>
</head><body><h1>RP2350 Control</h1>
<div class='sensor'>Temp: <b id='temp'>{temp_str}</b> C | Humidity: <b id='hum'>{hum_str}</b>%</div>
<div class='sensor' style='background:{door_color}'><b id='door'>{door_str}</b></div>
<h2>Relays</h2>"""

    for i in range(8):
        st = "ON" if relays[i].value() else "OFF"
        body += f"<div class='r'>Relay {i+1}: <b id='s{i}'>{st}</b> "
        body += f"<a href='/r?n={i+1}&s=1'><button class='on'>ON</button></a> "
        body += f"<a href='/r?n={i+1}&s=0'><button class='off'>OFF</button></a> "
        body += f"<button class='pulse' onclick='pulse({i+1},this)'>PULSE</button></div>"

    body += "<hr><a href='/a?s=1'><button class='on'>ALL ON</button></a> "
    body += "<a href='/a?s=0'><button class='off'>ALL OFF</button></a> "
    body += "<a href='/log'><button style='background:#666;color:#fff;padding:6px 12px;border:none'>LOGS</button></a>"

    # GPIO status - disabled (causes socket timeout)
    # body += "<h2>GPIO</h2><pre>...</pre>"
    body += "</body></html>"

    # Build headers with Content-Length
    body_bytes = body.encode()
    headers = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body_bytes)}\r\nConnection: close\r\n\r\n"
    return headers.encode() + body_bytes

def handle_request(req):
    """Parse request and return response"""
    # Fast reject for favicon and other junk
    if b'favicon' in req or b'.js' in req or b'.css' in req or b'.png' in req:
        return b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

    if b'GET /p?' in req:
        # Pulse: toggle for 5 seconds then restore (non-blocking)
        try:
            s = req.decode()
            n = int(s.split('n=')[1].split(' ')[0].split('&')[0])
            if 1 <= n <= 8:
                old = relays[n-1].value()
                new_val = 1 - old
                relays[n-1].value(new_val)
                # Schedule restore in 5 seconds
                end_time = time.ticks_add(time.ticks_ms(), 5000)
                pulse_tasks.append((n-1, end_time, old))
                log(f"R{n} pulse start: {old}->{new_val}, restore in 5s")
            else:
                log(f"PULSE n={n} out of range")
        except Exception as e:
            log(f"PULSE error: {e}")
        return b"HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

    elif b'GET /r?' in req:
        try:
            s = req.decode()
            n = int(s.split('n=')[1].split('&')[0])
            v = int(s.split('s=')[1].split(' ')[0].split('&')[0])
            if 1 <= n <= 8:
                relays[n-1].value(v)
                log(f"R{n} -> {v}")
        except Exception as e:
            log(f"R error: {e}")
        return b"HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

    elif b'GET /a?' in req:
        try:
            s = req.decode()
            v = int(s.split('s=')[1].split(' ')[0])
            for i, r in enumerate(relays):
                r.value(v)
            log(f"ALL -> {v}")
        except Exception as e:
            log(f"ALL error: {e}")
        return b"HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

    elif b'GET /api' in req:
        # JSON API for AJAX updates
        t, h = read_dht()
        states = [relays[i].value() for i in range(8)]
        door = door_pin.value()
        json = '{"t":%s,"h":%s,"r":[%s],"d":%d}' % (
            t if t else 'null',
            h if h else 'null',
            ','.join(str(s) for s in states),
            door
        )
        headers = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(json)}\r\nConnection: close\r\n\r\n"
        return headers.encode() + json.encode()

    elif b'GET /log' in req:
        # Plain text logs (minimal)
        txt = "\n".join(logs[-5:])
        return f"HTTP/1.1 200 OK\r\nContent-Length: {len(txt)}\r\nConnection: close\r\n\r\n{txt}".encode()

    elif b'GET / ' in req:
        return html_page()

    return b"HTTP/1.1 404 Not Found\r\nContent-Length: 3\r\nConnection: close\r\n\r\n404"

# Main loop
SOCK = 0
print(f"\nStarting server on http://{ip[0]}.{ip[1]}.{ip[2]}.{ip[3]}:80")
print("=" * 40)

idle_count = 0
link_check = 0

while True:
    try:
        # Check pending pulse tasks
        check_pulses()

        # Check door state change
        door_now = door_pin.value()
        if door_now != last_door_state:
            last_door_state = door_now
            state_str = "CLOSED" if door_now else "OPEN"
            log(f"DOOR: {state_str}")
            print(f">>> DOOR STATE CHANGED: {state_str} <<<")

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
