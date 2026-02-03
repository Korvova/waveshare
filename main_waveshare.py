"""
HTTP Web Server for Waveshare RP2350-POE-ETH-8DI-8RO
Uses built-in network.WIZNET5K module
"""

from machine import Pin
import network
import socket
import time
import json

# === Configuration ===
STATIC_IP = '192.168.1.100'
SUBNET = '255.255.255.0'
GATEWAY = '192.168.1.1'
DNS = '8.8.8.8'

# Relay GPIO pins (17-24)
RELAY_PINS = [17, 18, 19, 20, 21, 22, 23, 24]

# === Relay Controller ===
class RelayController:
    def __init__(self):
        self.relays = [Pin(pin, Pin.OUT) for pin in RELAY_PINS]
        self.states = [0] * len(self.relays)
        # Initialize all relays to OFF
        for relay in self.relays:
            relay.value(0)
        print(f'Initialized {len(self.relays)} relays')

    def set_relay(self, relay_num, state):
        """Set relay state (relay_num: 1-8, state: 0 or 1)"""
        if relay_num < 1 or relay_num > len(self.relays):
            return False
        idx = relay_num - 1
        self.relays[idx].value(state)
        self.states[idx] = state
        print(f'Relay {relay_num} set to {"ON" if state else "OFF"}')
        return True

    def get_states(self):
        """Get all relay states as dict"""
        states = {}
        for i in range(len(self.relays)):
            states[f'relay_{i+1}'] = {'state': self.states[i]}
        return states

# === HTML Page ===
HTML_PAGE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Relay Control</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:#f0f0f0;padding:20px}
.container{max-width:1200px;margin:0 auto}
h1{text-align:center;color:#333;margin-bottom:30px}
.controls{text-align:center;margin-bottom:30px}
.controls button{background:#007bff;color:white;border:none;padding:12px 30px;margin:0 10px;border-radius:5px;cursor:pointer;font-size:16px}
.controls button:hover{background:#0056b3}
.controls button.danger{background:#dc3545}
.controls button.danger:hover{background:#c82333}
.relay-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}
.relay-card{background:white;border-radius:10px;padding:20px;box-shadow:0 2px 5px rgba(0,0,0,0.1)}
.relay-card h3{margin-bottom:15px;color:#333}
.status{padding:10px;border-radius:5px;text-align:center;font-weight:bold;margin-bottom:15px}
.status.on{background:#28a745;color:white}
.status.off{background:#6c757d;color:white}
.buttons{display:flex;gap:10px}
.buttons button{flex:1;padding:10px;border:none;border-radius:5px;cursor:pointer;font-size:14px}
.buttons button:first-child{background:#28a745;color:white}
.buttons button:first-child:hover{background:#218838}
.buttons button:last-child{background:#dc3545;color:white}
.buttons button:last-child:hover{background:#c82333}
.footer{text-align:center;margin-top:30px;color:#666}
</style>
</head><body>
<div class="container">
<h1>Relay Control Panel</h1>
<div class="controls">
<button onclick="allOn()">All ON</button>
<button class="danger" onclick="allOff()">All OFF</button>
<button onclick="refresh()">Refresh</button>
</div>
<div class="relay-grid" id="relays"></div>
<div class="footer"><p>Waveshare RP2350-POE-ETH-8DI-8RO</p><p>IP: 192.168.1.100</p></div>
</div>
<script>
async function setRelay(relay,state){
try{
const r=await fetch(`/api/relay/${relay}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:state})});
const d=await r.json();
if(d.success)updateStatus(relay,state);
}catch(e){console.error('Error:',e);alert('Failed to control relay');}
}
async function allOn(){
try{
const r=await fetch('/api/relays/all/on',{method:'POST'});
const d=await r.json();
if(d.success)refresh();
}catch(e){console.error('Error:',e);}
}
async function allOff(){
try{
const r=await fetch('/api/relays/all/off',{method:'POST'});
const d=await r.json();
if(d.success)refresh();
}catch(e){console.error('Error:',e);}
}
function updateStatus(relay,state){
const el=document.getElementById(`status-${relay}`);
el.textContent=state?'ON':'OFF';
el.className='status '+(state?'on':'off');
}
async function loadRelays(){
try{
const r=await fetch('/api/relays');
const relays=await r.json();
const grid=document.getElementById('relays');
grid.innerHTML='';
for(let i=1;i<=8;i++){
const relay=relays[`relay_${i}`];
const card=document.createElement('div');
card.className='relay-card';
card.innerHTML=`<h3>Relay ${i}</h3>`+
`<div class="status ${relay.state?'on':'off'}" id="status-${i}">${relay.state?'ON':'OFF'}</div>`+
`<div class="buttons">`+
`<button onclick="setRelay(${i},1)">Turn ON</button>`+
`<button onclick="setRelay(${i},0)">Turn OFF</button>`+
`</div>`;
grid.appendChild(card);
}
}catch(e){console.error('Error loading relays:',e);}
}
function refresh(){location.reload();}
loadRelays();
setInterval(loadRelays,5000);
</script>
</body></html>"""

# === HTTP Server ===
class WebServer:
    def __init__(self, relay_controller):
        self.relay_controller = relay_controller
        self.server_socket = None

    def send_response(self, client, status, content_type, body):
        """Send HTTP response"""
        response = f"HTTP/1.1 {status}\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {len(body)}\r\n"
        response += "Connection: close\r\n\r\n"
        response += body
        client.send(response.encode('utf-8'))

    def handle_request(self, client):
        """Handle incoming HTTP request"""
        try:
            request = client.recv(2048).decode('utf-8')
            lines = request.split('\r\n')
            if not lines:
                return

            # Parse request line
            parts = lines[0].split(' ')
            if len(parts) < 2:
                return

            method = parts[0]
            uri = parts[1]

            print(f'{method} {uri}')

            # Route handling
            if method == 'GET':
                if uri == '/' or uri == '/index.html':
                    self.send_response(client, '200 OK', 'text/html', HTML_PAGE)
                elif uri == '/api/relays':
                    states = self.relay_controller.get_states()
                    self.send_response(client, '200 OK', 'application/json', json.dumps(states))
                else:
                    self.send_response(client, '404 Not Found', 'text/plain', 'Not Found')

            elif method == 'POST':
                if uri.startswith('/api/relay/'):
                    relay_num = int(uri.split('/')[-1])
                    # Parse JSON body
                    body_start = request.find('\r\n\r\n') + 4
                    body = request[body_start:]
                    data = json.loads(body)
                    state = data.get('state', 0)
                    success = self.relay_controller.set_relay(relay_num, state)
                    self.send_response(client, '200 OK', 'application/json',
                                     json.dumps({'success': success}))

                elif uri == '/api/relays/all/on':
                    for i in range(1, 9):
                        self.relay_controller.set_relay(i, 1)
                    self.send_response(client, '200 OK', 'application/json',
                                     json.dumps({'success': True}))

                elif uri == '/api/relays/all/off':
                    for i in range(1, 9):
                        self.relay_controller.set_relay(i, 0)
                    self.send_response(client, '200 OK', 'application/json',
                                     json.dumps({'success': True}))
                else:
                    self.send_response(client, '404 Not Found', 'text/plain', 'Not Found')

        except Exception as e:
            print(f'Error handling request: {e}')
        finally:
            client.close()

    def run(self):
        """Start HTTP server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', 80))
            self.server_socket.listen(5)
            print('HTTP Server listening on port 80')

            while True:
                client, addr = self.server_socket.accept()
                print(f'Client connected from {addr}')
                self.handle_request(client)

        except Exception as e:
            print(f'Server error: {e}')
        finally:
            if self.server_socket:
                self.server_socket.close()

# === Main Program ===
def main():
    print('='*50)
    print('Waveshare RP2350-POE-ETH-8DI-8RO')
    print('HTTP Relay Control Server')
    print('='*50)

    # Initialize relays
    print('\nInitializing relays...')
    relay_controller = RelayController()

    # Initialize Ethernet
    print('\nInitializing W5500 Ethernet...')
    try:
        nic = network.WIZNET5K()
        nic.active(True)
        nic.ifconfig((STATIC_IP, SUBNET, GATEWAY, DNS))
        print('Waiting for Ethernet connection...')

        for i in range(10):
            if nic.isconnected():
                break
            print('.', end='')
            time.sleep(1)

        print()
        if nic.isconnected():
            print('Ethernet connected!')
            info = nic.ifconfig()
            print(f'IP address: {info[0]}')
            print(f'Subnet: {info[1]}')
            print(f'Gateway: {info[2]}')
            print(f'DNS: {info[3]}')
        else:
            print('Warning: Ethernet not connected (check cable)')
            print('Starting server anyway...')

    except Exception as e:
        print(f'Ethernet init error: {e}')
        print('Starting server anyway...')

    # Start web server
    print('\n' + '='*50)
    print(f'Server starting at http://{STATIC_IP}')
    print('='*50 + '\n')

    server = WebServer(relay_controller)
    server.run()

if __name__ == '__main__':
    main()
