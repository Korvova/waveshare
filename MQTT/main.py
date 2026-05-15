"""
Fast local web UI + optional MQTT integration for Waveshare RP2350 relay board.

Design:
- Web UI always works over HTTP on board IP.
- Relay control is local HTTP API (fast and stable).
- MQTT is optional and can be enabled/disabled from the web page.
"""

from machine import Pin, SoftSPI, UART
from w5500_simple import W5500
import time
import json
import dht
import onewire
import ds18x20

# ===================== Hardware =====================
SPI_SCK = 34
SPI_MOSI = 35
SPI_MISO = 36
SPI_CS = 33
W5500_RST = 25
RELAY_PINS = [17, 18, 19, 20, 21, 22, 23, 24]
DHT_PIN = 42
DHT2_PIN = 41
DOOR1_PIN = 9   # DI1
DOOR2_PIN = 10  # DI2
DI_PINS = [11, 12, 13, 14, 15, 16]  # DI3..DI8
PZEM_TX = 40
PZEM_RX = 43

# ===================== Network =====================
MAC = [0x00, 0x08, 0xDC, 0x12, 0x34, 0x56]
IP = [192, 168, 1, 100]
GW = [192, 168, 1, 1]
SN = [255, 255, 255, 0]

# ===================== Files =====================
MQTT_CONFIG_FILE = "mqtt_config.json"

# ===================== Sockets =====================
SOCK_HTTP = 0
SOCK_MQTT = 1

# ===================== MQTT =====================
KEEPALIVE_SEC = 30
CLIENT_ID = "rp2350-relay-01"
HEARTBEAT_MS = 15000
SENSOR_POLL_MS = 2000
DHT_READ_MS = 30000
DS18_READ_MS = 3000
DS18_SCAN_MS = 5000

mqtt_cfg = {
    "enabled": False,
    "broker_ip": "192.168.1.10",
    "broker_port": 1883,
    "base_topic": "waveshare",
    "di_pull_modes": [1, 1, 1, 1, 1, 1],  # DI3..DI8: 1=PULL_UP(HIGH), 0=PULL_DOWN(LOW)
}

mqtt_connected = False
mqtt_rx_buffer = b""
last_mqtt_tx_ms = 0
last_mqtt_rx_ms = 0
last_mqtt_conn_try_ms = 0
last_heartbeat_ms = 0
packet_id = 1
last_sensor_poll_ms = 0
dht_last_read_ms = 0
dht_temp = None
dht_hum = None
dht2_temp = None
ds18_temps = []
ds18_last_read_ms = 0
ds18_last_scan_ms = 0
ds18_roms = []
dht_fail_count = 0
door_state = None
door2_state = None
di_states = [None, None, None, None, None, None]
pzem_cache = {"v": None, "a": None, "w": None}
pzem_last_read_ms = 0


def log(msg):
    print(msg)


def scan_ds18(force_log=False):
    global ds18_roms, ds18_last_scan_ms
    try:
        found = ds18.scan()
        ds18_roms = found if found else []
        ds18_last_scan_ms = time.ticks_ms()
        if force_log or ds18_roms:
            log("DS18B20 devices: %d" % len(ds18_roms))
    except:
        ds18_roms = []
        ds18_last_scan_ms = time.ticks_ms()
        if force_log:
            log("DS18B20 scan failed")
    return len(ds18_roms)


def load_mqtt_config():
    global mqtt_cfg
    try:
        with open(MQTT_CONFIG_FILE, "r") as f:
            data = json.loads(f.read())
            if isinstance(data, dict):
                mqtt_cfg["enabled"] = bool(data.get("enabled", False))
                mqtt_cfg["broker_ip"] = str(data.get("broker_ip", mqtt_cfg["broker_ip"]))
                mqtt_cfg["broker_port"] = int(data.get("broker_port", mqtt_cfg["broker_port"]))
                mqtt_cfg["base_topic"] = str(data.get("base_topic", mqtt_cfg["base_topic"]))
                pull_modes = data.get("di_pull_modes", mqtt_cfg["di_pull_modes"])
                if isinstance(pull_modes, list) and len(pull_modes) == 6:
                    mqtt_cfg["di_pull_modes"] = [1 if int(v) else 0 for v in pull_modes]
    except:
        pass


def save_mqtt_config():
    try:
        with open(MQTT_CONFIG_FILE, "w") as f:
            f.write(json.dumps(mqtt_cfg))
        return True
    except:
        return False


def parse_ip_string(ip_text):
    parts = ip_text.split(".")
    if len(parts) != 4:
        return None
    out = []
    try:
        for p in parts:
            v = int(p)
            if v < 0 or v > 255:
                return None
            out.append(v)
        return out
    except:
        return None


def topic_set_all():
    return "%s/relay/all/set" % mqtt_cfg["base_topic"]


def topic_set_relay(n):
    return "%s/relay/%d/set" % (mqtt_cfg["base_topic"], n)


def topic_state_relay(n):
    return "%s/relay/%d/state" % (mqtt_cfg["base_topic"], n)


def topic_online():
    return "%s/system/online" % mqtt_cfg["base_topic"]


def topic_heartbeat():
    return "%s/system/heartbeat" % mqtt_cfg["base_topic"]


def topic_state():
    return "%s/system/state" % mqtt_cfg["base_topic"]


def topic_get():
    return "%s/system/get" % mqtt_cfg["base_topic"]


def topic_temp():
    return "%s/sensor/temperature" % mqtt_cfg["base_topic"]


def topic_hum():
    return "%s/sensor/humidity" % mqtt_cfg["base_topic"]


def topic_temp2():
    return "%s/sensor2/temperature" % mqtt_cfg["base_topic"]


def topic_door():
    return "%s/door/state" % mqtt_cfg["base_topic"]


def topic_door2():
    return "%s/door2/state" % mqtt_cfg["base_topic"]


def encode_str(text):
    data = text.encode()
    return bytes([(len(data) >> 8) & 0xFF, len(data) & 0xFF]) + data


def encode_remaining_length(value):
    out = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value > 0:
            digit |= 0x80
        out.append(digit)
        if value == 0:
            break
    return bytes(out)


def decode_remaining_length_from_buffer(buf, start_idx):
    mul = 1
    value = 0
    idx = start_idx
    while True:
        if idx >= len(buf):
            return None, None
        b = buf[idx]
        idx += 1
        value += (b & 127) * mul
        if (b & 128) == 0:
            return value, idx
        mul *= 128
        if mul > 128 * 128 * 128 * 128:
            return None, None


def next_packet_id():
    global packet_id
    packet_id += 1
    if packet_id > 65535:
        packet_id = 1
    return packet_id


def mqtt_send(packet):
    global last_mqtt_tx_ms
    w5500.socket_send(SOCK_MQTT, packet)
    last_mqtt_tx_ms = time.ticks_ms()


def mqtt_publish(topic, payload, retain=False):
    if not mqtt_connected:
        return
    topic_b = topic.encode()
    payload_b = payload.encode()
    flags = 0x30 | (0x01 if retain else 0x00)
    body = bytes([(len(topic_b) >> 8) & 0xFF, len(topic_b) & 0xFF]) + topic_b + payload_b
    pkt = bytes([flags]) + encode_remaining_length(len(body)) + body
    mqtt_send(pkt)


def mqtt_publish_relay_state(relay_num):
    state = "ON" if relays[relay_num - 1].value() else "OFF"
    mqtt_publish(topic_state_relay(relay_num), state, retain=True)


def mqtt_publish_all_states():
    for n in range(1, 9):
        mqtt_publish_relay_state(n)


def mqtt_publish_online():
    mqtt_publish(topic_online(), "online", retain=True)


def mqtt_publish_sensor_values():
    if dht_temp is not None:
        mqtt_publish(topic_temp(), ("%.1f" % dht_temp), retain=True)
    if dht_hum is not None:
        mqtt_publish(topic_hum(), ("%.1f" % dht_hum), retain=True)
    if dht2_temp is not None:
        mqtt_publish(topic_temp2(), ("%.1f" % dht2_temp), retain=True)
    if door_state is not None:
        mqtt_publish(topic_door(), "CLOSED" if door_state else "OPEN", retain=True)
    if door2_state is not None:
        mqtt_publish(topic_door2(), "CLOSED" if door2_state else "OPEN", retain=True)


def mqtt_publish_heartbeat():
    payload = {
        "uptime_ms": time.ticks_ms(),
        "ip": "%d.%d.%d.%d" % tuple(IP),
        "mqtt_connected": mqtt_connected,
    }
    mqtt_publish(topic_heartbeat(), json.dumps(payload), retain=False)


def mqtt_publish_state_snapshot():
    payload = {
        "relays": [relays[i].value() for i in range(8)],
        "temp_c": dht_temp,
        "temp2_c": dht2_temp,
        "ds18_temps": ds18_temps,
        "ds18_count": len(ds18_roms),
        "hum_pct": dht_hum,
        "door_closed": door_state,
        "door2_closed": door2_state,
        "di": di_states,
        "di_pull_modes": mqtt_cfg["di_pull_modes"],
        "pz": pzem_cache,
        "mqtt_enabled": mqtt_cfg["enabled"],
        "mqtt_connected": mqtt_connected,
        "broker_ip": mqtt_cfg["broker_ip"],
        "broker_port": mqtt_cfg["broker_port"],
        "base_topic": mqtt_cfg["base_topic"],
        "uptime_ms": time.ticks_ms(),
        "ip": "%d.%d.%d.%d" % tuple(IP),
    }
    mqtt_publish(topic_state(), json.dumps(payload), retain=True)


def mqtt_socket_close():
    try:
        w5500.socket_close(SOCK_MQTT)
    except:
        pass


def mqtt_read_into_buffer():
    global mqtt_rx_buffer, last_mqtt_rx_ms
    avail = w5500.socket_recv_available(SOCK_MQTT)
    if avail <= 0:
        return
    chunk = w5500.socket_recv(SOCK_MQTT, min(avail, 1024))
    if chunk:
        mqtt_rx_buffer += chunk
        last_mqtt_rx_ms = time.ticks_ms()


def mqtt_pop_packet():
    global mqtt_rx_buffer
    if len(mqtt_rx_buffer) < 2:
        return None

    rem_len, header_end = decode_remaining_length_from_buffer(mqtt_rx_buffer, 1)
    if rem_len is None:
        return None

    total = header_end + rem_len
    if len(mqtt_rx_buffer) < total:
        return None

    pkt = mqtt_rx_buffer[:total]
    mqtt_rx_buffer = mqtt_rx_buffer[total:]
    return pkt


def mqtt_parse_publish(packet):
    rem_len, idx = decode_remaining_length_from_buffer(packet, 1)
    if rem_len is None:
        return None, None, 0

    hdr = packet[0]
    qos = (hdr >> 1) & 0x03

    topic_len = (packet[idx] << 8) | packet[idx + 1]
    idx += 2
    topic = packet[idx:idx + topic_len].decode()
    idx += topic_len

    msg_id = 0
    if qos > 0:
        msg_id = (packet[idx] << 8) | packet[idx + 1]
        idx += 2

    payload = packet[idx:].decode().strip()
    return topic, payload, msg_id


def mqtt_send_puback(msg_id):
    pkt = bytes([0x40, 0x02, (msg_id >> 8) & 0xFF, msg_id & 0xFF])
    mqtt_send(pkt)


def wait_socket_status(sock, target, timeout_ms=5000):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
        if w5500.socket_status(sock) == target:
            return True
        time.sleep_ms(20)
    return False


def mqtt_connect():
    global mqtt_connected, mqtt_rx_buffer, last_mqtt_tx_ms, last_mqtt_rx_ms, last_heartbeat_ms

    broker_ip = parse_ip_string(mqtt_cfg["broker_ip"])
    if broker_ip is None:
        log("MQTT config error: broker_ip")
        return False

    broker_port = int(mqtt_cfg["broker_port"])
    if broker_port <= 0 or broker_port > 65535:
        log("MQTT config error: broker_port")
        return False

    mqtt_socket_close()
    time.sleep_ms(20)

    if not w5500.socket_open(SOCK_MQTT, 0):
        return False

    w5500.socket_connect(SOCK_MQTT, broker_ip, broker_port)
    if not wait_socket_status(SOCK_MQTT, W5500.SOCK_ESTABLISHED, 1200):
        mqtt_socket_close()
        return False

    # CONNECT
    flags = 0x02
    vh = encode_str("MQTT") + bytes([0x04, flags, (KEEPALIVE_SEC >> 8) & 0xFF, KEEPALIVE_SEC & 0xFF])
    payload = encode_str(CLIENT_ID)
    pkt = bytes([0x10]) + encode_remaining_length(len(vh) + len(payload)) + vh + payload
    mqtt_send(pkt)

    # Wait CONNACK
    deadline = time.ticks_add(time.ticks_ms(), 1200)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        mqtt_read_into_buffer()
        p = mqtt_pop_packet()
        if p is None:
            time.sleep_ms(20)
            continue
        if (p[0] >> 4) == 2 and len(p) >= 4 and p[3] == 0x00:
            break
    else:
        mqtt_socket_close()
        return False

    # SUBSCRIBE to set topics + state request
    pid = next_packet_id()
    sub1 = encode_str("%s/relay/+/set" % mqtt_cfg["base_topic"]) + bytes([0])
    sub2 = encode_str(topic_set_all()) + bytes([0])
    sub3 = encode_str(topic_get()) + bytes([0])
    vh2 = bytes([(pid >> 8) & 0xFF, pid & 0xFF])
    payload2 = sub1 + sub2 + sub3
    subpkt = bytes([0x82]) + encode_remaining_length(len(vh2) + len(payload2)) + vh2 + payload2
    mqtt_send(subpkt)

    mqtt_connected = True
    mqtt_rx_buffer = b""
    now = time.ticks_ms()
    last_mqtt_tx_ms = now
    last_mqtt_rx_ms = now
    last_heartbeat_ms = now
    mqtt_publish_online()
    mqtt_publish_all_states()
    mqtt_publish_sensor_values()
    mqtt_publish_state_snapshot()
    mqtt_publish_heartbeat()
    log("MQTT connected")
    return True


def normalize_cmd(payload):
    p = payload.strip().upper()
    if p in ("1", "ON", "TRUE"):
        return 1
    if p in ("0", "OFF", "FALSE"):
        return 0
    if p == "TOGGLE":
        return 2
    return None


def sensor_loop_step():
    global dht_last_read_ms, dht_temp, dht_hum, dht2_temp, ds18_temps, ds18_last_read_ms, ds18_last_scan_ms, ds18_roms, dht_fail_count, dht_sensor, door_state, door2_state, di_states, pzem_last_read_ms, pzem_cache, last_sensor_poll_ms

    now = time.ticks_ms()
    if time.ticks_diff(now, last_sensor_poll_ms) < SENSOR_POLL_MS:
        return
    last_sensor_poll_ms = now

    # Door state: 1=closed, 0=open (pull-up wiring)
    new_door = 1 if door_pin.value() else 0
    door_changed = (door_state is None) or (new_door != door_state)
    if door_changed:
        door_state = new_door
        if mqtt_connected:
            mqtt_publish(topic_door(), "CLOSED" if door_state else "OPEN", retain=True)
            mqtt_publish_state_snapshot()

    new_door2 = 1 if door2_pin.value() else 0
    door2_changed = (door2_state is None) or (new_door2 != door2_state)
    if door2_changed:
        door2_state = new_door2
        if mqtt_connected:
            mqtt_publish(topic_door2(), "CLOSED" if door2_state else "OPEN", retain=True)
            mqtt_publish_state_snapshot()

    # DI3..DI8 states with configurable pull mode
    changed_di = False
    for i in range(6):
        raw = di_input_pins[i].value()
        if mqtt_cfg["di_pull_modes"][i] == 1:
            active = 1 if raw == 0 else 0
        else:
            active = 1 if raw == 1 else 0
        if di_states[i] is None or di_states[i] != active:
            di_states[i] = active
            changed_di = True
    if changed_di and mqtt_connected:
        mqtt_publish_state_snapshot()

    # PZEM read every 2 seconds
    if time.ticks_diff(now, pzem_last_read_ms) >= 2000:
        try:
            while pzem_uart.any():
                pzem_uart.read()
            cmd = bytes([0x01, 0x04, 0x00, 0x00, 0x00, 0x0A])
            crc = pzem_crc16(cmd)
            req = cmd + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
            pzem_uart.write(req)
            time.sleep_ms(120)
            if pzem_uart.any():
                r = pzem_uart.read()
                if r and len(r) >= 25:
                    pzem_cache = {
                        "v": ((r[3] << 8) | r[4]) / 10.0,
                        "a": ((r[5] << 8) | r[6] | (r[7] << 16) | (r[8] << 24)) / 1000.0,
                        "w": ((r[9] << 8) | r[10] | (r[11] << 16) | (r[12] << 24)) / 10.0,
                    }
                    if mqtt_connected:
                        mqtt_publish_state_snapshot()
            pzem_last_read_ms = now
        except:
            pass

    # DHT read with cache interval
    if time.ticks_diff(now, dht_last_read_ms) >= DHT_READ_MS or dht_temp is None:
        try:
            dht_sensor.measure()
            new_temp = dht_sensor.temperature()
            new_hum = dht_sensor.humidity()
            dht_last_read_ms = now
            dht_fail_count = 0

            changed = (
                dht_temp is None
                or dht_hum is None
                or abs(new_temp - dht_temp) >= 0.1
                or abs(new_hum - dht_hum) >= 0.1
            )

            dht_temp = new_temp
            dht_hum = new_hum

            if changed and mqtt_connected:
                mqtt_publish_sensor_values()
                mqtt_publish_state_snapshot()
        except:
            # Auto-recover DHT without rebooting board.
            dht_fail_count += 1
            if dht_fail_count >= 3:
                try:
                    dht_sensor = dht.DHT22(Pin(DHT_PIN))
                    dht_fail_count = 0
                    # force quick retry after re-init
                    dht_last_read_ms = time.ticks_add(now, -DHT_READ_MS)
                except:
                    pass

    # Second temperature sensor on GPIO41: DS18B20 (1-Wire)
    if (not ds18_roms) and time.ticks_diff(now, ds18_last_scan_ms) >= DS18_SCAN_MS:
        scan_ds18()

    if ds18_roms and time.ticks_diff(now, ds18_last_read_ms) >= DS18_READ_MS:
        try:
            ds18.convert_temp()
            time.sleep_ms(750)
            new_temps = []
            changed = len(ds18_temps) != len(ds18_roms)
            for i in range(len(ds18_roms)):
                temp = ds18.read_temp(ds18_roms[i])
                if isinstance(temp, float) and -55.0 <= temp <= 125.0:
                    new_temps.append(temp)
                    if not changed:
                        previous = ds18_temps[i]
                        if previous is None or abs(temp - previous) >= 0.1:
                            changed = True
                else:
                    new_temps.append(None)
                    if (not changed) and ds18_temps[i] is not None:
                        changed = True
            if changed:
                ds18_temps = new_temps
                dht2_temp = ds18_temps[0] if ds18_temps else None
                if mqtt_connected:
                    mqtt_publish_sensor_values()
                    mqtt_publish_state_snapshot()
            ds18_last_read_ms = now
        except:
            ds18_roms = []
            ds18_temps = []
            dht2_temp = None
            ds18_last_read_ms = now
            if mqtt_connected:
                mqtt_publish_state_snapshot()


def apply_relay(idx, cmd, source="unknown"):
    if idx < 0 or idx >= 8:
        return

    if cmd == 2:
        val = 0 if relays[idx].value() else 1
    else:
        val = 1 if cmd else 0

    relays[idx].value(val)
    if mqtt_connected:
        mqtt_publish_relay_state(idx + 1)
        mqtt_publish_state_snapshot()


def apply_all(cmd, source="unknown"):
    for i in range(8):
        apply_relay(i, cmd, source)


def mqtt_handle_packet(packet):
    pkt_type = (packet[0] >> 4) & 0x0F
    if pkt_type != 3:
        return

    topic, payload, msg_id = mqtt_parse_publish(packet)
    if topic is None:
        return

    if topic == topic_get():
        if mqtt_connected:
            mqtt_publish_all_states()
            mqtt_publish_sensor_values()
            mqtt_publish_state_snapshot()
            mqtt_publish_heartbeat()
    else:
        cmd = normalize_cmd(payload)
        if cmd is None:
            return

        if topic == topic_set_all():
            apply_all(cmd, source="mqtt")
        else:
            parts = topic.split("/")
            if len(parts) == 4 and parts[0] == mqtt_cfg["base_topic"] and parts[1] == "relay" and parts[3] == "set":
                try:
                    n = int(parts[2])
                    if 1 <= n <= 8:
                        apply_relay(n - 1, cmd, source="mqtt")
                except:
                    pass

    if msg_id:
        mqtt_send_puback(msg_id)


def mqtt_loop_step():
    global mqtt_connected, last_mqtt_conn_try_ms, last_heartbeat_ms

    if not mqtt_cfg["enabled"]:
        if mqtt_connected:
            mqtt_connected = False
            mqtt_socket_close()
        return

    if not w5500.get_link_status():
        mqtt_connected = False
        mqtt_socket_close()
        return

    if w5500.socket_status(SOCK_MQTT) != W5500.SOCK_ESTABLISHED:
        mqtt_connected = False

    if not mqtt_connected:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_mqtt_conn_try_ms) >= 2500:
            last_mqtt_conn_try_ms = now
            mqtt_connect()
        return

    mqtt_read_into_buffer()
    while True:
        pkt = mqtt_pop_packet()
        if pkt is None:
            break
        mqtt_handle_packet(pkt)

    now = time.ticks_ms()
    if time.ticks_diff(now, last_mqtt_tx_ms) > (KEEPALIVE_SEC * 1000) // 2:
        mqtt_send(bytes([0xC0, 0x00]))

    if time.ticks_diff(now, last_mqtt_rx_ms) > (KEEPALIVE_SEC * 1000 * 2):
        mqtt_connected = False
        mqtt_socket_close()
        return

    if time.ticks_diff(now, last_heartbeat_ms) >= HEARTBEAT_MS:
        mqtt_publish_heartbeat()
        last_heartbeat_ms = now


def html_page():
    relay_rows = []
    for i in range(8):
        state = "ON" if relays[i].value() else "OFF"
        css = "on" if state == "ON" else "off"
        relay_name = "Реле %d" % (i + 1)
        if i == 6:
            relay_name = "Реле 7 (вентилятор)"
        relay_rows.append(
            "<div class='relay'>%s: <span id='r%d' class='state %s'>%s</span> "
            "<button class='btn on' onclick='setRelay(%d,\"ON\")'>ON</button> "
            "<button class='btn off' onclick='setRelay(%d,\"OFF\")'>OFF</button> "
            "<button class='btn tgl' onclick='setRelay(%d,\"TOGGLE\")'>TOGGLE</button>"
            "</div>" % (relay_name, i + 1, css, state, i + 1, i + 1, i + 1)
        )

    ip_text = "%d.%d.%d.%d" % (IP[0], IP[1], IP[2], IP[3])
    tips = (
        "<pre id='tips'></pre>"
        "<script>"
        "function renderTips(){"
        "const base=document.getElementById('baseTopic').value.trim()||'waveshare';"
        "const ip=document.getElementById('brokerIp').value.trim()||'192.168.1.10';"
        "const p=document.getElementById('brokerPort').value.trim()||'1883';"
        "let t='MQTT Topic Map\\n';"
        "t+='publish from board:\\n';"
        "t+='  '+base+'/relay/<1..8>/state  (ON|OFF, retained)\\n';"
        "t+='  '+base+'/sensor/temperature  (C, retained)\\n';"
        "t+='  '+base+'/sensor/humidity     (%, retained)\\n';"
        "t+='  '+base+'/door/state          (OPEN|CLOSED, retained)\\n';"
        "t+='  '+base+'/system/online      (online, retained)\\n';"
        "t+='  '+base+'/system/heartbeat   (json)\\n';"
        "t+='  '+base+'/system/state       (json, retained)\\n\\n';"
        "t+='subscribe by board (control):\\n';"
        "t+='  '+base+'/relay/<1..8>/set   (ON|OFF|TOGGLE|1|0)\\n';"
        "t+='  '+base+'/relay/all/set      (ON|OFF|TOGGLE|1|0)\\n';"
        "t+='  '+base+'/system/get         (any payload => publish state)\\n\\n';"
        "t+='MQTT publish examples\\n';"
        "t+='mosquitto_pub -h '+ip+' -p '+p+' -t '+base+'/relay/1/set -m ON\\n';"
        "t+='mosquitto_pub -h '+ip+' -p '+p+' -t '+base+'/relay/all/set -m OFF\\n\\n';"
        "t+='Request full state\\n';"
        "t+='mosquitto_pub -h '+ip+' -p '+p+' -t '+base+'/system/get -m now\\n\\n';"
        "t+='Subscribe states\\n';"
        "t+='mosquitto_sub -h '+ip+' -p '+p+' -t '+base+'/relay/+/state -v\\n';"
        "t+='mosquitto_sub -h '+ip+' -p '+p+' -t '+base+'/system/# -v\\n\\n';"
        "t+='Broker is configured manually above (IP/Port).\\n';"
        "t+='Board uses that same broker for both publish and subscribe.';"
        "document.getElementById('tips').textContent=t;"
        "}"
        "</script>"
    )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>RP2350 Control</title>"
        "<style>"
        "body{font-family:Arial;margin:16px;background:#f7f9fc;color:#1f2937}"
        "h1{margin:0 0 8px 0}.card{background:#fff;border-radius:10px;padding:12px;margin:10px 0;box-shadow:0 1px 4px rgba(0,0,0,.08)}"
        ".relay{padding:8px 0;border-bottom:1px solid #eef2f7}.relay:last-child{border-bottom:none}"
        ".state{display:inline-block;min-width:52px;text-align:center;padding:3px 8px;border-radius:8px;font-weight:bold}"
        ".state.on{background:#166534;color:#fff}.state.off{background:#b91c1c;color:#fff}"
        ".btn{border:none;padding:6px 10px;border-radius:8px;color:#fff;cursor:pointer}"
        ".btn.on{background:#16a34a}.btn.off{background:#dc2626}.btn.tgl{background:#2563eb}"
        ".line{margin:6px 0}.ok{color:#166534}.bad{color:#b91c1c}"
        ".sensor-block{background:#f1f5f9;border-radius:8px;padding:8px 10px;margin:8px 0}"
        ".sensor-title{font-weight:bold;margin-bottom:4px}"
        "input{padding:6px;border:1px solid #cbd5e1;border-radius:6px;width:180px}"
        "label{display:inline-block;min-width:110px}"
        "pre{background:#0f172a;color:#e2e8f0;padding:10px;border-radius:8px;white-space:pre-wrap}"
        "</style></head><body>"
        "<h1>RP2350 Relay Control</h1>"
        "<div class='line'>Board IP: <b>" + ip_text + "</b></div>"
        "<div class='card'>"
        "<h3>Sensors</h3>"
        "<div class='sensor-block'><div class='sensor-title'>DHT22 (GPIO42)</div>"
        "<div class='line'>Temperature: <b id='tempVal'>--</b> C</div>"
        "<div class='line'>Humidity: <b id='humVal'>--</b> %</div></div>"
        "<div class='sensor-block'><div class='sensor-title'>DS18B20 (GPIO41)</div>"
        "<div class='line'>Temperature 2: <b id='temp2Val'>--</b> C</div>"
        "<div class='line'>Detected: <b id='ds18CountVal'>--</b></div>"
        "<div class='line'>All DS18B20: <b id='ds18ListVal'>--</b></div></div>"
        "<div class='line'>Voltage: <b id='pzV'>--</b> V | Current: <b id='pzA'>--</b> A | Power: <b id='pzW'>--</b> W</div>"
        "<div class='line'>Door 1 (DI1): <b id='doorVal'>--</b></div>"
        "<div class='line'>Door 2 (DI2): <b id='door2Val'>--</b></div>"
        "<div class='line'>DI3..DI8 active: <b id='diVals'>--</b></div>"
        "</div>"
        "<div class='card'>"
        "<h3>Relays</h3>" + "".join(relay_rows) +
        "<div class='line' style='margin-top:10px'>"
        "<button class='btn on' onclick='setAll(\"ON\")'>ALL ON</button> "
        "<button class='btn off' onclick='setAll(\"OFF\")'>ALL OFF</button> "
        "<button class='btn tgl' onclick='setAll(\"TOGGLE\")'>ALL TOGGLE</button>"
        "</div></div>"
        "<div class='card'>"
        "<h3>MQTT Settings</h3>"
        "<div class='line'><label>Enable MQTT</label><input id='mqttEnabled' type='checkbox'></div>"
        "<div class='line'><label>Broker IP</label><input id='brokerIp' value=''></div>"
        "<div class='line'><label>Broker Port</label><input id='brokerPort' value='1883'></div>"
        "<div class='line'><label>Base Topic</label><input id='baseTopic' value='waveshare'></div>"
        "<div class='line'><button class='btn tgl' onclick='saveMqtt()'>Save MQTT Config</button> "
        "<button class='btn on' onclick='testMqtt()'>Test MQTT</button></div>"
        "<div class='line'>MQTT status: <b id='mqttStatus'>-</b></div>"
        "<div class='line' id='saveResult'></div>"
        "<div class='line' id='testResult'></div>"
        "<h4>DI3..DI8 Door Contacts</h4>"
        "<div class='line'>Shows real contact state for door locks: CLOSED/OPEN.</div>"
        "<div class='line'>DI3: <b id='diState3'>--</b> | Logic <button class='btn on' onclick='setDiMode(3,\"HIGH\")'>ACTIVE=CLOSED</button> <button class='btn off' onclick='setDiMode(3,\"LOW\")'>ACTIVE=OPEN</button> <span id='diMode3'>-</span></div>"
        "<div class='line'>DI4: <b id='diState4'>--</b> | Logic <button class='btn on' onclick='setDiMode(4,\"HIGH\")'>ACTIVE=CLOSED</button> <button class='btn off' onclick='setDiMode(4,\"LOW\")'>ACTIVE=OPEN</button> <span id='diMode4'>-</span></div>"
        "<div class='line'>DI5: <b id='diState5'>--</b> | Logic <button class='btn on' onclick='setDiMode(5,\"HIGH\")'>ACTIVE=CLOSED</button> <button class='btn off' onclick='setDiMode(5,\"LOW\")'>ACTIVE=OPEN</button> <span id='diMode5'>-</span></div>"
        "<div class='line'>DI6: <b id='diState6'>--</b> | Logic <button class='btn on' onclick='setDiMode(6,\"HIGH\")'>ACTIVE=CLOSED</button> <button class='btn off' onclick='setDiMode(6,\"LOW\")'>ACTIVE=OPEN</button> <span id='diMode6'>-</span></div>"
        "<div class='line'>DI7: <b id='diState7'>--</b> | Logic <button class='btn on' onclick='setDiMode(7,\"HIGH\")'>ACTIVE=CLOSED</button> <button class='btn off' onclick='setDiMode(7,\"LOW\")'>ACTIVE=OPEN</button> <span id='diMode7'>-</span></div>"
        "<div class='line'>DI8: <b id='diState8'>--</b> | Logic <button class='btn on' onclick='setDiMode(8,\"HIGH\")'>ACTIVE=CLOSED</button> <button class='btn off' onclick='setDiMode(8,\"LOW\")'>ACTIVE=OPEN</button> <span id='diMode8'>-</span></div>"
        "<h4>How to control from any device</h4>" + tips +
        "</div>"
        "<script>"
        "async function jget(u){const r=await fetch(u);return await r.json();}"
        "async function jpost(u,obj){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});return await r.json();}"
        "let mqttDirty=false;"
        "function paintState(arr){for(let i=1;i<=8;i++){const el=document.getElementById('r'+i);const on=arr[i-1]===1;el.textContent=on?'ON':'OFF';el.className='state '+(on?'on':'off');}}"
        "async function refreshState(){try{const d=await jget('/api/state');paintState(d.relays||[]);"
        "document.getElementById('tempVal').textContent=(d.temp_c==null)?'--':Number(d.temp_c).toFixed(1);"
        "document.getElementById('temp2Val').textContent=(d.temp2_c==null)?'--':Number(d.temp2_c).toFixed(1);"
        "document.getElementById('ds18CountVal').textContent=(d.ds18_count==null)?'--':d.ds18_count;"
        "document.getElementById('ds18ListVal').textContent=(d.ds18_temps&&d.ds18_temps.length)?d.ds18_temps.map((v,i)=>'T'+(i+1)+': '+(v==null?'--':Number(v).toFixed(1)+' C')).join(' | '):'--';"
        "document.getElementById('humVal').textContent=(d.hum_pct==null)?'--':Number(d.hum_pct).toFixed(1);"
        "if(d.pz){document.getElementById('pzV').textContent=(d.pz.v==null)?'--':Number(d.pz.v).toFixed(1);document.getElementById('pzA').textContent=(d.pz.a==null)?'--':Number(d.pz.a).toFixed(3);document.getElementById('pzW').textContent=(d.pz.w==null)?'--':Number(d.pz.w).toFixed(1);}"
        "document.getElementById('doorVal').textContent=(d.door_closed===1)?'CLOSED':((d.door_closed===0)?'OPEN':'--');"
        "document.getElementById('door2Val').textContent=(d.door2_closed===1)?'CLOSED':((d.door2_closed===0)?'OPEN':'--');"
        "if(d.di&&d.di.length===6){document.getElementById('diVals').textContent=d.di.map((v,i)=>'DI'+(i+3)+':'+(v?'CLOSED':'OPEN')).join('  ');for(let i=0;i<6;i++){document.getElementById('diState'+(i+3)).textContent=d.di[i]?'CLOSED':'OPEN';}}"
        "if(d.di_pull_modes&&d.di_pull_modes.length===6){for(let i=0;i<6;i++){document.getElementById('diMode'+(i+3)).textContent=(d.di_pull_modes[i]===1)?'ACTIVE=CLOSED':'ACTIVE=OPEN';}}"
        "document.getElementById('mqttStatus').textContent=d.mqtt_connected?'connected':'disconnected';"
        "document.getElementById('mqttStatus').className=d.mqtt_connected?'ok':'bad';"
        "if(!mqttDirty){"
        "document.getElementById('mqttEnabled').checked=!!d.mqtt_enabled;"
        "if(document.activeElement.id!=='brokerIp')document.getElementById('brokerIp').value=d.broker_ip||'';"
        "if(document.activeElement.id!=='brokerPort')document.getElementById('brokerPort').value=d.broker_port||1883;"
        "if(document.activeElement.id!=='baseTopic')document.getElementById('baseTopic').value=d.base_topic||'waveshare';"
        "}"
        "renderTips();}catch(e){document.getElementById('mqttStatus').textContent='offline';document.getElementById('mqttStatus').className='bad';}}"
        "async function setRelay(n,s){await jpost('/api/relay',{relay:n,state:s});setTimeout(refreshState,60);}"
        "async function setAll(s){await jpost('/api/relay',{all:s});setTimeout(refreshState,60);}"
        "async function setDiMode(di,mode){await jpost('/api/di/config',{di:di,mode:mode});setTimeout(refreshState,80);}"
        "async function saveMqtt(){const payload={enabled:document.getElementById('mqttEnabled').checked,broker_ip:document.getElementById('brokerIp').value.trim(),broker_port:parseInt(document.getElementById('brokerPort').value,10),base_topic:document.getElementById('baseTopic').value.trim()};"
        "const r=await jpost('/api/mqtt/config',payload);document.getElementById('saveResult').textContent=r.ok?'Saved':'Save error';if(r.ok){mqttDirty=false;}renderTips();setTimeout(refreshState,150);}"
        "async function testMqtt(){try{const r=await jpost('/api/mqtt/test',{});document.getElementById('testResult').textContent=r.ok?('Publish OK: '+r.topic+' '+r.payload):('Test error: '+(r.error||'unknown'));}catch(e){document.getElementById('testResult').textContent='Test request failed';}}"
        "document.getElementById('mqttEnabled').addEventListener('change',()=>{mqttDirty=true;});"
        "document.getElementById('brokerIp').addEventListener('input',()=>{mqttDirty=true;});"
        "document.getElementById('brokerPort').addEventListener('input',()=>{mqttDirty=true;});"
        "document.getElementById('baseTopic').addEventListener('input',()=>{mqttDirty=true;});"
        "setInterval(refreshState,400);refreshState();"
        "</script>"
        "</body></html>"
    )

    b = html.encode()
    h = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(b)
    return h.encode() + b


def state_json_response():
    payload = {
        "relays": [relays[i].value() for i in range(8)],
        "temp_c": dht_temp,
        "temp2_c": dht2_temp,
        "ds18_temps": ds18_temps,
        "ds18_count": len(ds18_roms),
        "hum_pct": dht_hum,
        "door_closed": door_state,
        "door2_closed": door2_state,
        "di": di_states,
        "di_pull_modes": mqtt_cfg["di_pull_modes"],
        "pz": pzem_cache,
        "mqtt_connected": mqtt_connected,
        "mqtt_enabled": mqtt_cfg["enabled"],
        "broker_ip": mqtt_cfg["broker_ip"],
        "broker_port": mqtt_cfg["broker_port"],
        "base_topic": mqtt_cfg["base_topic"],
    }
    txt = json.dumps(payload)
    h = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(txt)
    return h.encode() + txt.encode()


def json_response(obj, code=200):
    txt = json.dumps(obj)
    if code == 200:
        line = "HTTP/1.1 200 OK"
    elif code == 400:
        line = "HTTP/1.1 400 Bad Request"
    else:
        line = "HTTP/1.1 500 Internal Server Error"
    h = "%s\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (line, len(txt))
    return h.encode() + txt.encode()


def pzem_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def parse_http(req_bytes):
    try:
        text = req_bytes.decode()
    except:
        return None, None, {}, ""

    pos = text.find("\r\n\r\n")
    if pos < 0:
        head = text
        body = ""
    else:
        head = text[:pos]
        body = text[pos + 4:]

    lines = head.split("\r\n")
    if not lines:
        return None, None, {}, body

    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None, None, {}, body

    method = parts[0]
    path = parts[1]
    headers = {}
    for line in lines[1:]:
        p = line.find(":")
        if p > 0:
            k = line[:p].strip().lower()
            v = line[p + 1:].strip()
            headers[k] = v

    return method, path, headers, body


def handle_api_relay(body_text):
    try:
        d = json.loads(body_text)
    except:
        return json_response({"ok": False, "error": "json"}, 400)

    if "relay" in d and "state" in d:
        try:
            relay = int(d["relay"])
            cmd = normalize_cmd(str(d["state"]))
            if relay < 1 or relay > 8 or cmd is None:
                return json_response({"ok": False, "error": "args"}, 400)
            apply_relay(relay - 1, cmd, source="web")
            return json_response({"ok": True})
        except:
            return json_response({"ok": False, "error": "args"}, 400)

    if "all" in d:
        cmd = normalize_cmd(str(d["all"]))
        if cmd is None:
            return json_response({"ok": False, "error": "args"}, 400)
        apply_all(cmd, source="web")
        return json_response({"ok": True})

    return json_response({"ok": False, "error": "args"}, 400)


def handle_api_mqtt_config(body_text):
    global mqtt_connected
    try:
        d = json.loads(body_text)
    except:
        return json_response({"ok": False, "error": "json"}, 400)

    try:
        enabled = bool(d.get("enabled", mqtt_cfg["enabled"]))
        broker_ip = str(d.get("broker_ip", mqtt_cfg["broker_ip"]))
        broker_port = int(d.get("broker_port", mqtt_cfg["broker_port"]))
        base_topic = str(d.get("base_topic", mqtt_cfg["base_topic"]))

        if parse_ip_string(broker_ip) is None:
            return json_response({"ok": False, "error": "broker_ip"}, 400)
        if broker_port <= 0 or broker_port > 65535:
            return json_response({"ok": False, "error": "broker_port"}, 400)
        if not base_topic:
            return json_response({"ok": False, "error": "base_topic"}, 400)

        mqtt_cfg["enabled"] = enabled
        mqtt_cfg["broker_ip"] = broker_ip
        mqtt_cfg["broker_port"] = broker_port
        mqtt_cfg["base_topic"] = base_topic

        save_ok = save_mqtt_config()

        # force reconnect with new config
        mqtt_connected = False
        mqtt_socket_close()

        return json_response({"ok": save_ok})
    except:
        return json_response({"ok": False}, 500)


def handle_api_mqtt_test():
    global mqtt_connected
    if not mqtt_cfg["enabled"]:
        return json_response({"ok": False, "error": "mqtt_disabled"}, 400)

    if not mqtt_connected:
        if not mqtt_connect():
            return json_response({"ok": False, "error": "connect_failed"}, 500)

    try:
        test_topic = "%s/test" % mqtt_cfg["base_topic"]
        msg = "ping:%d" % time.ticks_ms()
        mqtt_publish(test_topic, msg, retain=False)
        return json_response({"ok": True, "topic": test_topic, "payload": msg})
    except:
        mqtt_connected = False
        mqtt_socket_close()
        return json_response({"ok": False, "error": "publish_failed"}, 500)


def apply_di_pull_mode(di_num, mode_text):
    if di_num < 3 or di_num > 8:
        return False
    idx = di_num - 3
    mode = str(mode_text).strip().upper()
    if mode == "HIGH":
        di_input_pins[idx] = Pin(DI_PINS[idx], Pin.IN, Pin.PULL_UP)
        mqtt_cfg["di_pull_modes"][idx] = 1
    elif mode == "LOW":
        di_input_pins[idx] = Pin(DI_PINS[idx], Pin.IN, Pin.PULL_DOWN)
        mqtt_cfg["di_pull_modes"][idx] = 0
    else:
        return False
    save_mqtt_config()
    return True


def handle_api_di_config(body_text):
    try:
        d = json.loads(body_text)
        di = int(d.get("di", 0))
        mode = str(d.get("mode", ""))
    except:
        return json_response({"ok": False, "error": "args"}, 400)
    if not apply_di_pull_mode(di, mode):
        return json_response({"ok": False, "error": "args"}, 400)
    return json_response({"ok": True})


def handle_http_request(req_bytes):
    method, path, headers, body = parse_http(req_bytes)
    if method is None:
        return b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

    if method == "GET" and path == "/":
        return html_page()

    if method == "GET" and path == "/api/state":
        return state_json_response()

    if method == "POST" and path == "/api/relay":
        return handle_api_relay(body)

    if method == "POST" and path == "/api/mqtt/config":
        return handle_api_mqtt_config(body)

    if method == "POST" and path == "/api/mqtt/test":
        return handle_api_mqtt_test()

    if method == "POST" and path == "/api/di/config":
        return handle_api_di_config(body)

    return b"HTTP/1.1 404 Not Found\r\nContent-Length: 3\r\nConnection: close\r\n\r\n404"


def http_loop_step():
    st = w5500.socket_status(SOCK_HTTP)

    if st == W5500.SOCK_CLOSED:
        w5500.socket_open(SOCK_HTTP, 80)
        return

    if st == W5500.SOCK_INIT:
        w5500.socket_listen(SOCK_HTTP)
        return

    if st == W5500.SOCK_LISTEN_STATUS:
        return

    if st == W5500.SOCK_ESTABLISHED:
        # collect request bytes
        deadline = time.ticks_add(time.ticks_ms(), 200)
        req = b""
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            avail = w5500.socket_recv_available(SOCK_HTTP)
            if avail > 0:
                req += w5500.socket_recv(SOCK_HTTP, min(avail, 1024))
                if b"\r\n\r\n" in req:
                    # if body exists, try to read expected length
                    try:
                        text = req.decode()
                        hpos = text.find("\r\n\r\n")
                        head = text[:hpos]
                        body_now = len(text) - (hpos + 4)
                        need = 0
                        for ln in head.split("\r\n"):
                            if ln.lower().startswith("content-length:"):
                                need = int(ln.split(":", 1)[1].strip())
                                break
                        if body_now >= need:
                            break
                    except:
                        break
            else:
                time.sleep_ms(5)

        if req:
            resp = handle_http_request(req)
            w5500.socket_send(SOCK_HTTP, resp)
            time.sleep_ms(5)

        w5500.socket_disconnect(SOCK_HTTP)
        time.sleep_ms(5)
        w5500.socket_close(SOCK_HTTP)
        return

    if st == W5500.SOCK_CLOSE_WAIT:
        w5500.socket_disconnect(SOCK_HTTP)
        return

    w5500.socket_close(SOCK_HTTP)


# ===================== Init =====================
relays = [Pin(p, Pin.OUT, value=0) for p in RELAY_PINS]
door_pin = Pin(DOOR1_PIN, Pin.IN, Pin.PULL_UP)
door2_pin = Pin(DOOR2_PIN, Pin.IN, Pin.PULL_UP)
di_input_pins = [Pin(p, Pin.IN, Pin.PULL_UP) for p in DI_PINS]
pzem_uart = UART(1, baudrate=9600, tx=Pin(PZEM_TX), rx=Pin(PZEM_RX))
dht_sensor = dht.DHT22(Pin(DHT_PIN))
ds18 = ds18x20.DS18X20(onewire.OneWire(Pin(DHT2_PIN)))
scan_ds18(force_log=True)

cs = Pin(SPI_CS, Pin.OUT, value=1)
rst = Pin(W5500_RST, Pin.OUT)
spi = SoftSPI(
    baudrate=2000000,
    polarity=0,
    phase=0,
    sck=Pin(SPI_SCK),
    mosi=Pin(SPI_MOSI),
    miso=Pin(SPI_MISO),
)

w5500 = W5500(spi, cs, rst)
w5500.set_mac(MAC)
w5500.set_gateway(GW)
w5500.set_subnet(SN)
w5500.set_ip(IP)

load_mqtt_config()

# Apply saved pull mode for DI3..DI8 after loading config
for i in range(6):
    pull_mode = Pin.PULL_UP if mqtt_cfg["di_pull_modes"][i] == 1 else Pin.PULL_DOWN
    di_input_pins[i] = Pin(DI_PINS[i], Pin.IN, pull_mode)

log("Fast Web UI firmware started")
log("HTTP: http://%d.%d.%d.%d" % tuple(IP))
log("MQTT enabled: %s" % mqtt_cfg["enabled"])

# ===================== Main loop =====================
while True:
    try:
        sensor_loop_step()
        mqtt_loop_step()
        http_loop_step()
        time.sleep_ms(10)
    except Exception as e:
        log("Loop error: %s" % e)
        mqtt_connected = False
        try:
            w5500.socket_close(SOCK_HTTP)
        except:
            pass
        mqtt_socket_close()
        time.sleep_ms(100)
