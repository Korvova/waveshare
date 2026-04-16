"""
Simple Web Server for Waveshare RP2350-POE-ETH-8DI-8RO
Using custom W5500 driver
"""
from machine import Pin, SoftSPI, UART
from w5500_simple import W5500
import dht
import time
import json
import os

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

# PZEM-004T power meter (UART)
PZEM_TX = 40
PZEM_RX = 43

# ============= MONITORING CONFIGURATION =============
CONFIG_FILE = 'monitor_config.json'
LOG_FILE = 'monitor_log.txt'
LOG_FILE_OLD = 'monitor_log_old.txt'
MAX_LOG_SIZE = 1024 * 1024  # 1 MB

# Default monitoring config
DEFAULT_CONFIG = {
    "enabled": False,
    "server_ip": "",
    "server_port": 8080,
    "interval": 300,
    "devices": []
}

# Monitoring state
monitor_config = DEFAULT_CONFIG.copy()
monitor_enabled = False
monitor_devices = {}  # {ip: {status, ms, last_check}}
monitor_last_run = 0
monitor_current_index = 0

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

# ============= CONFIGURATION FUNCTIONS =============
def load_config():
    """Load monitoring config from file"""
    global monitor_config
    try:
        with open(CONFIG_FILE, 'r') as f:
            monitor_config = json.load(f)
            log(f"Config loaded: {len(monitor_config.get('devices', []))} devices")
            return True
    except:
        monitor_config = DEFAULT_CONFIG.copy()
        log("No config found, using defaults")
        return False

def save_config():
    """Save monitoring config to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(monitor_config, f)
        log("Config saved")
        return True
    except Exception as e:
        log(f"Config save error: {e}")
        return False

# ============= LOG FUNCTIONS =============
def write_monitor_log(ip, status, ms):
    """Write monitor log entry to flash with rotation"""
    try:
        # Check file size and rotate if needed
        try:
            size = os.stat(LOG_FILE)[6]
            if size >= MAX_LOG_SIZE:
                # Rotate: current -> old
                try:
                    os.remove(LOG_FILE_OLD)
                except:
                    pass
                os.rename(LOG_FILE, LOG_FILE_OLD)
                log("Log rotated")
        except:
            pass  # File doesn't exist yet

        # Append new entry
        timestamp = time.time()
        entry = f"{timestamp}|{ip}|{status}|{ms}\n"
        with open(LOG_FILE, 'a') as f:
            f.write(entry)
    except Exception as e:
        log(f"Log write error: {e}")

def read_monitor_logs(limit=100):
    """Read last N log entries"""
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            return lines[-limit:] if len(lines) > limit else lines
    except:
        return []

# ============= MONITORING ENGINE =============
def check_host(ip_str, port=80, timeout_ms=500):
    """Check if host is alive via TCP connect"""
    global w5500
    SOCK_CHECK = 1  # Use socket 1 for monitoring

    try:
        # Parse IP string to list
        ip = [int(x) for x in ip_str.split('.')]

        # Close socket if it's not closed
        w5500.socket_close(SOCK_CHECK)
        time.sleep_ms(10)

        # Open socket
        if not w5500.socket_open(SOCK_CHECK, 0):  # Port 0 = auto-assign
            return False, 0

        # Try to connect
        start = time.ticks_ms()
        w5500.socket_connect(SOCK_CHECK, ip, port)

        # Wait for connection or timeout
        deadline = time.ticks_add(start, timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            status = w5500.socket_status(SOCK_CHECK)
            if status == W5500.SOCK_ESTABLISHED:
                elapsed = time.ticks_diff(time.ticks_ms(), start)
                w5500.socket_close(SOCK_CHECK)
                return True, elapsed
            elif status == W5500.SOCK_CLOSED:
                break
            time.sleep_ms(10)

        # Timeout or failed
        w5500.socket_close(SOCK_CHECK)
        return False, 0

    except Exception as e:
        log(f"Check error {ip_str}: {e}")
        try:
            w5500.socket_close(SOCK_CHECK)
        except:
            pass
        return False, 0

def monitor_step():
    """Check one device per call (non-blocking)"""
    global monitor_devices, monitor_current_index, monitor_config, monitor_last_run

    if not monitor_config.get('enabled', False):
        return

    devices = monitor_config.get('devices', [])
    if not devices:
        return

    # Check if enough time passed since last run
    now = time.ticks_ms()
    if monitor_current_index == 0:  # Starting new cycle
        interval_ms = monitor_config.get('interval', 300) * 1000
        if time.ticks_diff(now, monitor_last_run) < interval_ms:
            return
        monitor_last_run = now

    # Check current device
    if monitor_current_index < len(devices):
        ip = devices[monitor_current_index]
        online, ms = check_host(ip)
        status = "online" if online else "offline"

        # Update state
        monitor_devices[ip] = {
            'status': status,
            'ms': ms,
            'last_check': time.time()
        }

        # Log to flash
        write_monitor_log(ip, status, ms)

        # Next device
        monitor_current_index += 1

        # If finished all devices, send statistics
        if monitor_current_index >= len(devices):
            monitor_current_index = 0
            send_statistics()

def send_statistics():
    """Send monitoring statistics to server"""
    global monitor_devices, monitor_config, w5500

    server_ip = monitor_config.get('server_ip', '')
    server_port = monitor_config.get('server_port', 8080)

    if not server_ip:
        return

    try:
        # Build JSON packet
        devices_list = []
        for ip, data in monitor_devices.items():
            devices_list.append({
                'ip': ip,
                'status': data['status'],
                'ms': data['ms']
            })

        packet = {
            'board_id': 'RP2350_01',
            'timestamp': time.time(),
            'devices': devices_list
        }

        json_data = json.dumps(packet)

        # Send via HTTP POST
        SOCK_STATS = 2  # Use socket 2 for statistics
        server_ip_list = [int(x) for x in server_ip.split('.')]

        w5500.socket_close(SOCK_STATS)
        time.sleep_ms(10)

        if w5500.socket_open(SOCK_STATS, 0):
            if w5500.socket_connect(SOCK_STATS, server_ip_list, server_port):
                # Wait for connection
                for _ in range(50):
                    if w5500.socket_status(SOCK_STATS) == W5500.SOCK_ESTABLISHED:
                        break
                    time.sleep_ms(10)

                # Send HTTP POST
                http_req = f"POST /stats HTTP/1.1\r\nHost: {server_ip}\r\nContent-Type: application/json\r\nContent-Length: {len(json_data)}\r\n\r\n{json_data}"
                w5500.socket_send(SOCK_STATS, http_req.encode())
                time.sleep_ms(100)

            w5500.socket_close(SOCK_STATS)

        log(f"Stats sent: {len(devices_list)} devices")

    except Exception as e:
        log(f"Stats send error: {e}")

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

# PZEM-004T power meter
pzem_uart = UART(1, baudrate=9600, tx=Pin(PZEM_TX), rx=Pin(PZEM_RX))
print(f"PZEM on TX={PZEM_TX}, RX={PZEM_RX}")

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

# Load monitoring config
load_config()

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

# PZEM cache
pzem_cache = {'v': None, 'a': None, 'w': None, 'wh': None, 'hz': None, 'pf': None}
pzem_last_read = 0

def pzem_crc16(data):
    """Calculate Modbus CRC16"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def read_pzem():
    """Read PZEM-004T power meter (cached 2s, expires after 5s)"""
    global pzem_cache, pzem_last_read
    now = time.ticks_ms()
    # Only read every 2 seconds
    if time.ticks_diff(now, pzem_last_read) < 2000 and pzem_cache['v'] is not None:
        return pzem_cache
    # If cache is older than 5s, clear it (PZEM not responding)
    if time.ticks_diff(now, pzem_last_read) > 5000:
        pzem_cache = {'v': None, 'a': None, 'w': None, 'wh': None, 'hz': None, 'pf': None}
    try:
        # Clear buffer
        while pzem_uart.any():
            pzem_uart.read()
        # Send read command
        cmd = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A])
        crc = pzem_crc16(cmd)
        cmd = cmd + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        pzem_uart.write(cmd)
        time.sleep_ms(100)
        if pzem_uart.any():
            r = pzem_uart.read()
            if len(r) >= 25:
                pzem_cache = {
                    'v': (r[3] << 8 | r[4]) / 10.0,
                    'a': (r[5] << 8 | r[6] | r[7] << 24 | r[8] << 16) / 1000.0,
                    'w': (r[9] << 8 | r[10] | r[11] << 24 | r[12] << 16) / 10.0,
                    'wh': r[13] << 8 | r[14] | r[15] << 24 | r[16] << 16,
                    'hz': (r[17] << 8 | r[18]) / 10.0,
                    'pf': (r[19] << 8 | r[20]) / 100.0
                }
                pzem_last_read = now
    except:
        pass
    return pzem_cache

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
    # PZEM power meter
    pz = read_pzem()
    pz_v = f"{pz['v']:.1f}" if pz['v'] else "--"
    pz_a = f"{pz['a']:.2f}" if pz['a'] is not None else "--"
    pz_w = f"{pz['w']:.1f}" if pz['w'] is not None else "--"

    # Build body first (no auto-refresh, use AJAX)
    body = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'><title>RP2350</title>
<style>body{{font-family:Arial;margin:20px}}
.sensor{{background:#2196F3;color:#fff;padding:20px;border-radius:10px;margin:10px 0;font-size:20px}}
.power{{background:#9C27B0;color:#fff;padding:20px;border-radius:10px;margin:10px 0;font-size:18px}}
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
if(d.pz){{document.getElementById('pz_v').innerText=d.pz.v?d.pz.v.toFixed(1):'--';
document.getElementById('pz_a').innerText=d.pz.a!=null?d.pz.a.toFixed(2):'--';
document.getElementById('pz_w').innerText=d.pz.w!=null?d.pz.w.toFixed(1):'--';}}
}}).catch(()=>{{}});
}}
function monStart(){{
fetch('/api/monitor/start',{{method:'POST'}}).then(()=>{{
document.getElementById('mon_status').innerText='Running';
}});
}}
function monStop(){{
fetch('/api/monitor/stop',{{method:'POST'}}).then(()=>{{
document.getElementById('mon_status').innerText='Stopped';
}});
}}
setInterval(upd,2000);
</script>
</head><body><h1>RP2350 Control</h1>
<div class='sensor'>Temp: <b id='temp'>{temp_str}</b> C | Humidity: <b id='hum'>{hum_str}</b>%</div>
<div class='sensor' style='background:{door_color}'><b id='door'>{door_str}</b></div>
<div class='power'>⚡ <b id='pz_v'>{pz_v}</b> V | <b id='pz_a'>{pz_a}</b> A | <b id='pz_w'>{pz_w}</b> W</div>
<h2>Network Monitor</h2>
<div style='background:#607D8B;color:#fff;padding:15px;border-radius:10px;margin:10px 0'>
Status: <b id='mon_status'>{'Running' if monitor_config.get('enabled', False) else 'Stopped'}</b> |
Devices: <b id='mon_count'>{len(monitor_config.get('devices', []))}</b> |
Online: <b id='mon_online'>{sum(1 for d in monitor_devices.values() if d.get('status')=='online')}</b>
<br><button onclick='monStart()' style='background:#4CAF50;color:#fff;padding:8px 16px;border:none;margin:5px;cursor:pointer'>START</button>
<button onclick='monStop()' style='background:#f44336;color:#fff;padding:8px 16px;border:none;margin:5px;cursor:pointer'>STOP</button>
<a href='/config'><button style='background:#2196F3;color:#fff;padding:8px 16px;border:none;margin:5px'>CONFIG</button></a>
</div>
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

def config_page():
    """Config page for monitoring settings"""
    devices_str = '\n'.join(monitor_config.get('devices', []))
    server_ip = monitor_config.get('server_ip', '')
    server_port = monitor_config.get('server_port', 8080)
    interval = monitor_config.get('interval', 300)

    html = f"""<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Monitor Config</title>
<style>body{{font-family:Arial;margin:20px}}
input,textarea{{width:100%;padding:8px;margin:5px 0;box-sizing:border-box}}
button{{background:#4CAF50;color:white;padding:10px 20px;border:none;cursor:pointer;margin:10px 5px 0 0}}
.back{{background:#666}}
</style>
</head><body>
<h1>Network Monitor Configuration</h1>
<form id='configForm'>
<label>Server IP (for statistics):</label>
<input type='text' id='server_ip' value='{server_ip}' placeholder='192.168.1.5'>
<label>Server Port:</label>
<input type='number' id='server_port' value='{server_port}'>
<label>Check Interval (seconds):</label>
<input type='number' id='interval' value='{interval}'>
<label>Devices to Monitor (one IP per line):</label>
<textarea id='devices' rows='15' placeholder='192.168.1.1&#10;192.168.1.2&#10;...'>{devices_str}</textarea>
<button type='button' onclick='saveConfig()'>SAVE</button>
<a href='/'><button type='button' class='back'>BACK</button></a>
<div id='status' style='margin-top:10px;color:green'></div>
</form>
<script>
function saveConfig(){{
var devices = document.getElementById('devices').value.split('\\n').filter(x=>x.trim());
var config = {{
  server_ip: document.getElementById('server_ip').value,
  server_port: parseInt(document.getElementById('server_port').value),
  interval: parseInt(document.getElementById('interval').value),
  devices: devices
}};
fetch('/api/config',{{
  method:'POST',
  headers:{{'Content-Type':'application/json'}},
  body:JSON.stringify(config)
}}).then(r=>r.json()).then(d=>{{
  document.getElementById('status').innerText='Config saved! '+devices.length+' devices.';
  setTimeout(()=>{{document.getElementById('status').innerText=''}},3000);
}});
}}
</script>
</body></html>"""

    body_bytes = html.encode()
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
        pz = read_pzem()
        pz_json = '"pz":{"v":%s,"a":%s,"w":%s}' % (
            pz['v'] if pz['v'] else 'null',
            pz['a'] if pz['a'] is not None else 'null',
            pz['w'] if pz['w'] is not None else 'null'
        )
        json = '{"t":%s,"h":%s,"r":[%s],"d":%d,%s}' % (
            t if t else 'null',
            h if h else 'null',
            ','.join(str(s) for s in states),
            door,
            pz_json
        )
        headers = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(json)}\r\nConnection: close\r\n\r\n"
        return headers.encode() + json.encode()

    elif b'GET /log' in req:
        # Plain text logs (minimal)
        txt = "\n".join(logs[-5:])
        return f"HTTP/1.1 200 OK\r\nContent-Length: {len(txt)}\r\nConnection: close\r\n\r\n{txt}".encode()

    elif b'POST /api/monitor/start' in req:
        # Start monitoring
        monitor_config['enabled'] = True
        save_config()
        log("Monitor started")
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 17\r\nConnection: close\r\n\r\n{\"status\":\"ok\"}"

    elif b'POST /api/monitor/stop' in req:
        # Stop monitoring
        monitor_config['enabled'] = False
        save_config()
        log("Monitor stopped")
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 17\r\nConnection: close\r\n\r\n{\"status\":\"ok\"}"

    elif b'GET /api/monitor' in req:
        # Get monitoring status
        devices_json = []
        for ip, data in monitor_devices.items():
            devices_json.append('{"ip":"%s","status":"%s","ms":%d}' % (ip, data['status'], data['ms']))
        json_str = '{"enabled":%s,"devices":[%s]}' % (
            'true' if monitor_config.get('enabled', False) else 'false',
            ','.join(devices_json)
        )
        headers = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(json_str)}\r\nConnection: close\r\n\r\n"
        return headers.encode() + json_str.encode()

    elif b'POST /api/config' in req:
        # Save configuration
        try:
            # Parse JSON from POST body
            s = req.decode()
            body_start = s.find('\r\n\r\n')
            if body_start > 0:
                body = s[body_start+4:]
                config_data = json.loads(body)
                monitor_config.update(config_data)
                save_config()
                log("Config updated")
                return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 17\r\nConnection: close\r\n\r\n{\"status\":\"ok\"}"
        except Exception as e:
            log(f"Config update error: {e}")
        return b"HTTP/1.1 400 Bad Request\r\nContent-Length: 20\r\nConnection: close\r\n\r\n{\"status\":\"error\"}"

    elif b'GET /config' in req:
        return config_page()

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

        # Run monitoring step (non-blocking)
        monitor_step()

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
