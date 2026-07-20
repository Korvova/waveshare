"""
Локальный предпросмотр веб-интерфейса прошивки (для скриншотов на ПК).

Зачем: main.py написан под MicroPython и работает только на плате Unirack-1
(RP2350; модули machine, w5500_simple, dht, onewire, ds18x20, time.ticks_*).
Этот скрипт подменяет «железные» модули заглушками, переиспользует НАСТОЯЩИЕ
функции веб-интерфейса из main.py (html_page, handle_http_request, /api/*)
и поднимает тот же сайт на обычном Python.

Запуск:
    python local_preview.py
    python local_preview.py 9000        # другой порт

Потом открой в браузере:  http://localhost:8080
Реле реально переключаются, датчики показывают демо-значения.
Это копия интерфейса платы — удобно для скриншотов без платы.
"""

import sys
import os
import types
import random
import threading
import time as _real_time
import webbrowser
import socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(HERE, "main.py")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080


# --------------------------------------------------------------------------
# 1. Заглушки «железных» модулей MicroPython, чтобы main.py импортировался
# --------------------------------------------------------------------------
class _Pin:
    IN = 0
    OUT = 1
    PULL_UP = 2
    PULL_DOWN = 3

    def __init__(self, pin_id=None, mode=-1, pull=-1, value=None, **kw):
        self._id = pin_id
        # реле создаются с value=0; входы по умолчанию читаем как 1 (PULL_UP)
        self._v = 0 if value is not None else 1

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = 1 if v else 0
        return None

    def __call__(self, v=None):
        return self.value(v)


class _SoftSPI:
    def __init__(self, *a, **k):
        pass


class _UART:
    def __init__(self, *a, **k):
        pass

    def any(self):
        return 0

    def read(self, *a):
        return None

    def write(self, *a):
        return None


def _machine_reset():
    pass


machine = types.ModuleType("machine")
machine.Pin = _Pin
machine.SoftSPI = _SoftSPI
machine.UART = _UART
machine.reset = _machine_reset


class _W5500:
    # константы статусов сокета (значения не важны для предпросмотра)
    SOCK_CLOSED = 0
    SOCK_INIT = 1
    SOCK_LISTEN_STATUS = 2
    SOCK_ESTABLISHED = 3
    SOCK_CLOSE_WAIT = 4

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        # set_mac/set_ip/socket_* и т.п. — глушим всё, что вызовет main.py
        def _noop(*a, **k):
            return 0
        return _noop


w5500_simple = types.ModuleType("w5500_simple")
w5500_simple.W5500 = _W5500


class _DHT22:
    def __init__(self, *a, **k):
        pass

    def measure(self):
        pass

    def temperature(self):
        return 23.0

    def humidity(self):
        return 45.0


dht_mod = types.ModuleType("dht")
dht_mod.DHT22 = _DHT22
dht_mod.DHT11 = _DHT22


class _OneWire:
    def __init__(self, *a, **k):
        pass


onewire_mod = types.ModuleType("onewire")
onewire_mod.OneWire = _OneWire


class _DS18X20:
    def __init__(self, *a, **k):
        pass

    def scan(self):
        return []

    def convert_temp(self):
        pass

    def read_temp(self, rom):
        return None


ds18x20_mod = types.ModuleType("ds18x20")
ds18x20_mod.DS18X20 = _DS18X20

# time с тиками MicroPython поверх обычного time
fake_time = types.ModuleType("time")
fake_time.sleep = _real_time.sleep
fake_time.sleep_ms = lambda ms: _real_time.sleep(ms / 1000.0)
fake_time.sleep_us = lambda us: _real_time.sleep(us / 1000000.0)
fake_time.ticks_ms = lambda: int(_real_time.monotonic() * 1000)
fake_time.ticks_us = lambda: int(_real_time.monotonic() * 1000000)
fake_time.ticks_diff = lambda a, b: a - b
fake_time.ticks_add = lambda t, d: t + d

for name, mod in {
    "machine": machine,
    "w5500_simple": w5500_simple,
    "dht": dht_mod,
    "onewire": onewire_mod,
    "ds18x20": ds18x20_mod,
    "time": fake_time,
}.items():
    sys.modules[name] = mod


# --------------------------------------------------------------------------
# 2. Берём main.py, отрезаем бесконечный главный цикл и выполняем остальное.
#    Так мы получаем настоящие html_page() / handle_http_request() / API.
# --------------------------------------------------------------------------
with open(MAIN_PY, "r", encoding="utf-8") as f:
    src = f.read()

marker = "# ===================== Main loop ====================="
if marker in src:
    src = src.split(marker)[0]

ns = {"__name__": "main_preview"}
exec(compile(src, MAIN_PY, "exec"), ns)


# --------------------------------------------------------------------------
# 3. Демо-значения датчиков, чтобы интерфейс выглядел «как с платы»
# --------------------------------------------------------------------------
ns["dht_temp"] = 23.4          # DHT22 температура
ns["dht_hum"] = 44.0           # DHT22 влажность
ns["dht2_temp"] = 22.8         # первый DS18B20
ns["ds18_temps"] = [22.8, 23.6]
ns["ds18_roms"] = [b"\x28\x01", b"\x28\x02"]   # «найдено 2 датчика»
ns["door_state"] = 1           # Door 1 = CLOSED
ns["door2_state"] = 0          # Door 2 = OPEN
ns["di_states"] = [1, 0, 1, 0, 1, 0]           # DI3..DI8
ns["pzem_cache"] = {"v": 230.5, "a": 1.234, "w": 284.6}


def _animate():
    """Лёгкое «дыхание» значений, чтобы предпросмотр выглядел живым."""
    while True:
        ns["dht_temp"] = round(min(26.0, max(20.0, ns["dht_temp"] + random.uniform(-0.1, 0.1))), 1)
        ns["dht_hum"] = round(min(55.0, max(35.0, ns["dht_hum"] + random.uniform(-0.3, 0.3))), 1)
        v = round(230.0 + random.uniform(-0.6, 0.6), 1)
        a = round(max(0.0, 1.2 + random.uniform(-0.05, 0.05)), 3)
        ns["pzem_cache"] = {"v": v, "a": a, "w": round(v * a, 1)}
        ns["dht2_temp"] = round(min(26.0, max(20.0, ns["dht2_temp"] + random.uniform(-0.1, 0.1))), 1)
        ns["ds18_temps"] = [ns["dht2_temp"], round(ns["dht2_temp"] + 0.8, 1)]
        _real_time.sleep(1.5)


# --------------------------------------------------------------------------
# 4. Сырой TCP-сервер: отдаём байты запроса в настоящий handle_http_request
# --------------------------------------------------------------------------
handle_http_request = ns["handle_http_request"]


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        data = b""
        try:
            while True:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\r\n\r\n" in data:
                    head, _, rest = data.partition(b"\r\n\r\n")
                    need = 0
                    for ln in head.split(b"\r\n"):
                        if ln.lower().startswith(b"content-length:"):
                            try:
                                need = int(ln.split(b":", 1)[1].strip())
                            except Exception:
                                need = 0
                            break
                    if len(rest) >= need:
                        break
        except Exception:
            pass

        if not data:
            return
        try:
            resp = handle_http_request(data)
            self.request.sendall(resp)
        except Exception as e:
            body = ("preview error: %s" % e).encode()
            self.request.sendall(
                b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
                + body
            )


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    threading.Thread(target=_animate, daemon=True).start()

    url = "http://localhost:%d" % PORT
    print("=" * 56)
    print(" Локальный предпросмотр веб-интерфейса Unirack-1")
    print("=" * 56)
    print(" Открой в браузере:  %s" % url)
    print("               или:  http://127.0.0.1:%d" % PORT)
    print(" Остановить:         Ctrl+C")
    print("=" * 56)

    # открыть браузер автоматически (чуть позже старта сервера)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        with Server(("127.0.0.1", PORT), Handler) as srv:
            srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except OSError as e:
        print("\nНе удалось занять порт %d: %s" % (PORT, e))
        print("Попробуй другой порт:  python local_preview.py 9000")


if __name__ == "__main__":
    main()
