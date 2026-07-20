# Unirack-1 — Fast Web + MQTT (RP2350)

Прошивка Unirack-1: стабильная локальная вебка + опциональный MQTT.

## Назначение реле

| № | Название | Английское имя | Логика |
|---|----------|----------------|--------|
| 1 | Розетка 1 | PowerOutlet1 | НЗ-контакт: после подачи питания ВКЛ |
| 2 | Розетка 2 | PowerOutlet2 | НЗ-контакт: после подачи питания ВКЛ |
| 3 | Розетка 3 | PowerOutlet3 | НЗ-контакт: после подачи питания ВКЛ |
| 4 | Розетка 4 | PowerOutlet4 | НЗ-контакт: после подачи питания ВКЛ |
| 5 | Блок питания 1 | PowerSupply1 | НЗ-контакт: после подачи питания ВКЛ |
| 6 | Блок питания 2 | PowerSupply2 | НЗ-контакт: после подачи питания ВКЛ |
| 7 | Вентиляторы | FAN | НЗ-контакт: после подачи питания ВКЛ |
| 8 | Выход на контактор | ToContactor | НО-контакт: после подачи питания ВЫКЛ |

**Важно:** реле 1–7 коммутируют нагрузку через нормально-замкнутые контакты.
Прошивка это учитывает: везде (вебка, HTTP API, MQTT) состояние **логическое** —
`ON` = нагрузка запитана. Кнопка/команда `ON` включает нагрузку, `OFF` — выключает.
После подачи питания (и после сброса платы) реле 1–7 = `ON`, реле 8 = `OFF`.

## Цифровые входы

DI1 и DI2 на Unirack-1 **не выведены** и не используются.

| Вход | Название | Английское имя | Примечание |
|------|----------|----------------|------------|
| DI3 | Цифровой вход 1 | DigitalInput1 | |
| DI4 | Цифровой вход 2 | DigitalInput2 | |
| DI5 | Цифровой вход 3 | DigitalInput3 | |
| DI6 | Сброс настроек | Reset | Замкнуть на GND на ~2 с — сброс IP на 192.168.1.100 |
| DI7 | Дверь 1 | Door1 | Публикуется в `<base>/door/state` |
| DI8 | Дверь 2 | Door2 | Публикуется в `<base>/door2/state` |

### Логика дверных датчиков

Штатные датчики проверены: **при закрытии двери контакт замыкается**.
DI7/DI8 по умолчанию работают в прямой логике (`ACTIVE=CLOSED`): контакт
замкнут на GND → `CLOSED` (дверь закрыта), разомкнут → `OPEN` (дверь открыта).

**Как проверить датчик:** при закрытой двери в вебке должно быть `CLOSED`;
откройте дверь — должно стать `OPEN`. Если датчик другого типа и показания
обратные — нажмите `ACTIVE=OPEN` у DI7/DI8, настройка сохраняется.

## Разъёмы датчиков

- **Измеритель электропитания (EnergyMonitor)** — клеммы `EM TX / EM RX / +5 / GND`
  (GPIO40/GPIO43). Подключается измеритель питания, например PZEM-004T.
  Поставляется опционально.
- **Датчик температуры (TemperatureSensor)** — клеммы `TS Data / VDD / GND`
  (GPIO41, шина 1-Wire, 3.3 В). Параллельно подключаются датчики DS18B20
  (3 шт. в комплекте). Нужен один общий подтягивающий резистор 4.7 кОм
  между `TS Data` и `VDD` на всю линию.
- **Датчик температуры и влажности (TempHumSensor)** — клеммы `THS Data / VDD / GND`
  (GPIO42, 3.3 В). Подключается датчик DHT22 (1 шт. в комплекте).

## Что работает

- Быстрый веб-интерфейс: `http://192.168.1.100`
- Управление реле 1..8 (ON/OFF/TOGGLE) без перезагрузки страницы
- `TOGGLE` временно переключает реле на 5 секунд, затем возвращает прежнее состояние
- Настройки MQTT прямо в вебке (Enable, Broker IP, Broker Port, Base Topic)
- Кнопка `Test MQTT` в вебке
- MQTT publish + subscribe (двусторонняя работа)
- Дверь 1 (DI7) и Дверь 2 (DI8) в вебке, API и MQTT
- DI3..DI8 с отображением состояния `OPEN/CLOSED`
- Настройка логики DI3..DI8 из вебки (`ACTIVE=CLOSED` / `ACTIVE=OPEN`)

## Важно по архитектуре

- Плата работает как **MQTT client**.
- MQTT broker должен быть отдельным сетевым узлом (не на плате).
- Адрес брокера задается вручную в вебке (`Broker IP` + `Broker Port`).
- IP самой платы задается в вебке в блоке `Board Network` и применяется после перезагрузки.
- Для сброса IP платы на `192.168.1.100` замкните `DI6 (Reset)` на `GND/DGND` примерно
  на 2 секунды; плата сохранит дефолтный IP и перезагрузится. Вебка покажет индикатор
  сброса и через 5 секунд перейдет на дефолтный IP.

## MQTT Topic Map

Публикует плата:
- `<base>/relay/<1..8>/state` (`ON|OFF`, retained; `ON` = нагрузка запитана)
- `<base>/sensor/temperature` (DHT22, °C, retained)
- `<base>/sensor/humidity` (DHT22, %, retained)
- `<base>/sensor2/temperature` (первый DS18B20, °C, retained)
- `<base>/door/state` (Дверь 1 / DI7: `OPEN|CLOSED`, retained)
- `<base>/door2/state` (Дверь 2 / DI8: `OPEN|CLOSED`, retained)
- `<base>/system/online` (`online`, retained)
- `<base>/system/heartbeat` (JSON, периодически)
- `<base>/system/state` (JSON snapshot, retained)

Подписывается плата:
- `<base>/relay/<1..8>/set` (`ON|OFF|TOGGLE|1|0|TRUE|FALSE`), `TOGGLE` возвращает реле назад через 5 секунд
- `<base>/relay/all/set` (`ON|OFF|TOGGLE|1|0|TRUE|FALSE`), `TOGGLE` возвращает реле назад через 5 секунд
- `<base>/system/get` (любой payload -> плата публикует state/heartbeat)

`<base>` = значение поля `Base Topic` в вебке (по умолчанию `unirack1`).

## Примеры команд

```bash
# Управление (реле 1 = Розетка 1)
mosquitto_pub -h 192.168.1.10 -p 1883 -t unirack1/relay/1/set -m ON
mosquitto_pub -h 192.168.1.10 -p 1883 -t unirack1/relay/all/set -m OFF

# Запросить полный state
mosquitto_pub -h 192.168.1.10 -p 1883 -t unirack1/system/get -m now

# Подписка
mosquitto_sub -h 192.168.1.10 -p 1883 -t unirack1/relay/+/state -v
mosquitto_sub -h 192.168.1.10 -p 1883 -t unirack1/system/# -v
mosquitto_sub -h 192.168.1.10 -p 1883 -t unirack1/door/state -v
```

## Заливка на плату

```powershell
cd C:\Users\Владимир\Documents\App\waveshare\MQTT-2-0
mpremote connect COM13 cp w5500_simple.py :w5500_simple.py
mpremote connect COM13 cp main.py :main.py
mpremote connect COM13 reset
```

## Файлы

- `main.py` — основная прошивка (web + optional mqtt)
- `w5500_simple.py` — драйвер W5500 (добавлен `socket_connect`)
- `local_preview.py` — предпросмотр вебки на ПК без платы (`python local_preview.py`)
- `README_MQTT.md` — эта документация
- `ИНСТРУКЦИЯ.md` — инструкция пользователя
- `КОНТАКТЫ.md` — листик с названием контактов (клеммник)
- `CHECKLIST.md` — чек-лист проверки устройства

## API (HTTP)

- `GET /api/state` — текущее состояние
  - `relays` — логические состояния реле 1..8 (`1` = нагрузка запитана)
  - `door_closed` (Дверь 1 / DI7), `door2_closed` (Дверь 2 / DI8)
  - `di` для DI3..DI8
  - `di_pull_modes` для DI3..DI8
  - `temp2_c`, `ds18_temps` и `ds18_count` для DS18B20 (TS Data / GPIO41)
  - `board_ip`, `gateway`, `subnet` для сетевых настроек платы
- `POST /api/network/config` — сохранить IP платы, применяется после перезагрузки
  - `{"board_ip":"192.168.1.101","gateway":"192.168.1.1","subnet":"255.255.255.0"}`
- `POST /api/relay` — управление реле (логическое: `ON` = включить нагрузку)
  - `{"relay":7,"state":"OFF"}` — выключить вентиляторы
  - `{"all":"ON"}`
- `POST /api/di/config` — настройка логики DI3..DI8
  - `{"di":7,"mode":"HIGH"}` -> `ACTIVE=CLOSED` — дефолт: контакт замкнут = CLOSED
  - `{"di":7,"mode":"LOW"}` -> `ACTIVE=OPEN` — инверсия: контакт разомкнут = CLOSED
