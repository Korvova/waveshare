"""
W5500 Web Server for Waveshare RP2350-POE-ETH-8DI-8RO
Adapted from ESP32-Wiznet-W5500-Micropython
"""
from wiznet5k import WIZNET5K
from machine import Pin, SoftSPI
import wiznet5k_socket as socket
import time

# ============= RP2350B PIN CONFIGURATION =============
# W5500 SPI pins (from Waveshare schematic)
SPI_SCK  = 34
SPI_MOSI = 35
SPI_MISO = 36
SPI_CS   = 33
W5500_RST = 25

# Relay pins (GPIO 17-24)
RELAY_PINS = [17, 18, 19, 20, 21, 22, 23, 24]

# ============= INITIALIZE HARDWARE =============
print("=" * 40)
print("Waveshare RP2350-POE-ETH-8DI-8RO")
print("W5500 Web Server")
print("=" * 40)

# Initialize relays
relays = []
for pin in RELAY_PINS:
    relay = Pin(pin, Pin.OUT)
    relay.value(0)  # OFF
    relays.append(relay)
print("Relays initialized (all OFF)")

# Initialize SPI for W5500
print("Initializing W5500...")
cs = Pin(SPI_CS, Pin.OUT)
rst = Pin(W5500_RST, Pin.OUT)

# Hardware reset
rst.value(0)
time.sleep_ms(100)
rst.value(1)
time.sleep_ms(100)

# Use SoftSPI for custom pins (slower for stability)
spi = SoftSPI(
    baudrate=1000000,  # 1MHz - slow but stable
    polarity=0,
    phase=0,
    sck=Pin(SPI_SCK),
    mosi=Pin(SPI_MOSI),
    miso=Pin(SPI_MISO)
)
print(f"SPI configured: SCK={SPI_SCK}, MOSI={SPI_MOSI}, MISO={SPI_MISO}")

# Initialize WIZNET5K
nic = WIZNET5K(spi, cs, rst)

print("Chip Version:", nic.chip)
print("MAC Address:", [hex(i) for i in nic.mac_address])
print("IP Address:", nic.pretty_ip(nic.ip_address))
print("=" * 40)

# ============= RELAY CONTROL =============
def set_relay(num, state):
    """Set relay state (num: 1-8, state: 0 or 1)"""
    if 1 <= num <= 8:
        relays[num-1].value(state)
        return True
    return False

def get_relay(num):
    """Get relay state (num: 1-8)"""
    if 1 <= num <= 8:
        return relays[num-1].value()
    return 0

# ============= WEB SERVER =============
def generate_html():
    """Generate HTML page with relay controls"""
    html = """HTTP/1.1 200 OK\r
Content-Type: text/html\r
Connection: close\r
\r
<!DOCTYPE html><html><head>
<meta charset='UTF-8'>
<title>RP2350 Relay Control</title>
<style>
body{font-family:Arial;margin:20px;background:#f0f0f0;}
h1{color:#333;}
.relay{margin:10px 0;padding:15px;background:white;border-radius:5px;display:flex;align-items:center;justify-content:space-between;}
.on{background:#4CAF50;color:white;padding:10px 20px;border:none;cursor:pointer;border-radius:3px;}
.off{background:#f44336;color:white;padding:10px 20px;border:none;cursor:pointer;border-radius:3px;}
.status{font-weight:bold;padding:5px 10px;border-radius:3px;}
.status-on{background:#4CAF50;color:white;}
.status-off{background:#ccc;}
</style></head><body>
<h1>RP2350 Relay Control</h1>
<p>IP: """ + nic.pretty_ip(nic.ip_address) + """</p>
"""
    for i in range(1, 9):
        state = get_relay(i)
        status_class = "status-on" if state else "status-off"
        status_text = "ON" if state else "OFF"
        html += f"""<div class='relay'>
<span>Relay {i}: <span class='status {status_class}'>{status_text}</span></span>
<span>
<a href='/relay?n={i}&s=1'><button class='on'>ON</button></a>
<a href='/relay?n={i}&s=0'><button class='off'>OFF</button></a>
</span></div>"""

    html += """<hr>
<a href='/all?s=1'><button class='on'>ALL ON</button></a>
<a href='/all?s=0'><button class='off'>ALL OFF</button></a>
</body></html>"""
    return html

def handle_request(client_sock):
    """Handle incoming HTTP request"""
    try:
        request = client_sock.recv(1024).decode('utf-8')
        if not request:
            return

        # Parse first line
        first_line = request.split('\r\n')[0]
        print("Request:", first_line)

        # Parse URL
        if 'GET /relay?' in request:
            # /relay?n=1&s=1
            try:
                params = request.split('GET /relay?')[1].split(' ')[0]
                n = int(params.split('n=')[1].split('&')[0])
                s = int(params.split('s=')[1].split('&')[0].split(' ')[0])
                set_relay(n, s)
                print(f"Relay {n} -> {'ON' if s else 'OFF'}")
            except:
                pass
            # Redirect to main page
            client_sock.send(b"HTTP/1.1 302 Found\r\nLocation: /\r\n\r\n")

        elif 'GET /all?' in request:
            # /all?s=1
            try:
                s = int(request.split('s=')[1].split(' ')[0].split('&')[0])
                for i in range(1, 9):
                    set_relay(i, s)
                print(f"All relays -> {'ON' if s else 'OFF'}")
            except:
                pass
            client_sock.send(b"HTTP/1.1 302 Found\r\nLocation: /\r\n\r\n")

        elif 'GET / ' in request or 'GET /index' in request:
            # Main page
            html = generate_html()
            client_sock.send(html.encode())

        else:
            # 404
            client_sock.send(b"HTTP/1.1 404 Not Found\r\n\r\n404 Not Found")

    except Exception as e:
        print("Error:", e)
    finally:
        client_sock.close()

# ============= MAIN =============
print("\nStarting web server on port 80...")
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('0.0.0.0', 80))
server.listen(5)
print("Server running at http://" + nic.pretty_ip(nic.ip_address))
print("=" * 40)

while True:
    try:
        client, addr = server.accept()
        print(f"\nClient connected: {addr}")
        handle_request(client)
    except Exception as e:
        print("Server error:", e)
        time.sleep(1)
