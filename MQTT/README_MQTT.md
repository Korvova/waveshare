# Fast Web + MQTT (Waveshare RP2350)

Эта папка содержит отдельную прошивку с приоритетом на стабильную локальную вебку и опциональным MQTT.

## Что работает

- Быстрый веб-интерфейс: `http://192.168.1.100`
- Управление реле 1..8 (ON/OFF/TOGGLE) без перезагрузки страницы
- Настройки MQTT прямо в вебке (Enable, Broker IP, Broker Port, Base Topic)
- Кнопка `Test MQTT` в вебке
- MQTT publish + subscribe (двусторонняя работа)
- Door 1 (DI1/GPIO9) и Door 2 (DI2/GPIO10) в вебке и API
- DI3..DI8 (GPIO11..16) с отображением состояния `OPEN/CLOSED`
- Настройка логики DI3..DI8 из вебки (`ACTIVE=CLOSED` / `ACTIVE=OPEN`)

## DS18B20 на GPIO41

- Красный провод -> `3V3`
- Черный провод -> `GND`
- Желтый/белый провод -> `GPIO41`
- Резистор `4.7 kOhm` ставится между `DATA/GPIO41` и `3V3`
- Несколько DS18B20 можно подключить к одному `GPIO41`: все `DATA` вместе, все `3V3` вместе, все `GND` вместе
- Для нескольких датчиков нужен один общий подтягивающий резистор на всю 1-Wire линию; длинную "звезду" лучше заменить на линию/шину с короткими ответвлениями
- Если `temp2_c = null` и `ds18_count = 0`, плата не видит датчик на 1-Wire шине
- Если датчик был подключен после запуска, обновленная прошивка пересканирует DS18B20 автоматически

## Важно по архитектуре

- Плата работает как **MQTT client**.
- MQTT broker должен быть отдельным сетевым узлом (не на плате).
- Адрес брокера задается вручную в вебке (`Broker IP` + `Broker Port`).
- IP самой платы задается в вебке в блоке `Board Network` и применяется после перезагрузки.
- Для сброса IP платы на `192.168.1.100` замкните `DI6` на `GND/DGND` примерно на 2 секунды; плата сохранит дефолтный IP и перезагрузится. Вебка покажет индикатор `Сброс по DI6` и через 5 секунд перейдет на дефолтный IP.

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

## API (HTTP)

- `GET /api/state` — текущее состояние
  - `door_closed` (DI1), `door2_closed` (DI2)
  - `di` для DI3..DI8
  - `di_pull_modes` для DI3..DI8
  - `temp2_c`, `ds18_temps` и `ds18_count` для DS18B20 на GPIO41
  - `board_ip`, `gateway`, `subnet` для сетевых настроек платы
- `POST /api/network/config` — сохранить IP платы, применяется после перезагрузки
  - `{"board_ip":"192.168.1.101","gateway":"192.168.1.1","subnet":"255.255.255.0"}`
- `POST /api/relay` — управление реле
  - `{"relay":7,"state":"OFF"}`
  - `{"all":"ON"}`
- `POST /api/di/config` — настройка логики DI3..DI8
  - `{"di":3,"mode":"HIGH"}` -> `ACTIVE=CLOSED`
  - `{"di":3,"mode":"LOW"}` -> `ACTIVE=OPEN`
