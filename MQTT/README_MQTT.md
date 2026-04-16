# Fast Web + MQTT (Waveshare RP2350)

Эта папка содержит отдельную прошивку с приоритетом на стабильную локальную вебку и опциональным MQTT.

## Что работает

- Быстрый веб-интерфейс: `http://192.168.1.100`
- Управление реле 1..8 (ON/OFF/TOGGLE) без перезагрузки страницы
- Настройки MQTT прямо в вебке (Enable, Broker IP, Broker Port, Base Topic)
- Кнопка `Test MQTT` в вебке
- MQTT publish + subscribe (двусторонняя работа)

## Важно по архитектуре

- Плата работает как **MQTT client**.
- MQTT broker должен быть отдельным сетевым узлом (не на плате).
- Адрес брокера задается вручную в вебке (`Broker IP` + `Broker Port`).

## MQTT Topic Map

Публикует плата:
- `<base>/relay/<1..8>/state` (`ON|OFF`, retained)
- `<base>/system/online` (`online`, retained)
- `<base>/system/heartbeat` (JSON, периодически)
- `<base>/system/state` (JSON snapshot, retained)

Подписывается плата:
- `<base>/relay/<1..8>/set` (`ON|OFF|TOGGLE|1|0|TRUE|FALSE`)
- `<base>/relay/all/set` (`ON|OFF|TOGGLE|1|0|TRUE|FALSE`)
- `<base>/system/get` (любой payload -> плата публикует state/heartbeat)

`<base>` = значение поля `Base Topic` в вебке (по умолчанию `waveshare`).

## Примеры команд

```bash
# Управление
mosquitto_pub -h 192.168.1.10 -p 1884 -t waveshare/relay/1/set -m ON
mosquitto_pub -h 192.168.1.10 -p 1884 -t waveshare/relay/all/set -m OFF

# Запросить полный state
mosquitto_pub -h 192.168.1.10 -p 1884 -t waveshare/system/get -m now

# Подписка
mosquitto_sub -h 192.168.1.10 -p 1884 -t waveshare/relay/+/state -v
mosquitto_sub -h 192.168.1.10 -p 1884 -t waveshare/system/# -v
```

## Заливка на плату

```powershell
cd C:\Users\Владимир\Documents\App\waveshare\MQTT
mpremote connect COM13 cp w5500_simple.py :w5500_simple.py
mpremote connect COM13 cp main.py :main.py
mpremote connect COM13 reset
```

## Файлы

- `main.py` — основная прошивка (web + optional mqtt)
- `w5500_simple.py` — драйвер W5500 (добавлен `socket_connect`)
- `README_MQTT.md` — эта документация
