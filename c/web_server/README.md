# HTTP Relay Control Server - C Version

Веб-сервер на C для управления 8 реле на плате Waveshare RP2350-POE-ETH-8DI-8RO.

## Статус проекта

⚠️ **ВАЖНО**: Этот проект требует компиляции с Pico SDK и библиотеками Waveshare.

Для быстрого старта **рекомендуется использовать готовые примеры Waveshare** в качестве основы.

## Что создано

1. ✅ [config.h](config.h) - конфигурация сети и GPIO
2. ✅ [web_pages.h](web_pages.h) - встроенный HTML интерфейс
3. ✅ [main.c](main.c) - основной код HTTP сервера
4. ⚠️ CMakeLists.txt - требует настройки под Waveshare библиотеки

## Альтернатива: Адаптация готового MQTT примера Waveshare

**Рекомендуемый подход** для быстрого результата:

### Шаг 1: Использовать готовый пример как основу

```bash
cd RP2350-ETH-8DI-8RO/C/02-MQTT/examples
cp main.c main_backup.c
```

### Шаг 2: Заменить MQTT логику на HTTP

В файле `main.c`:
1. Удалить весь MQTT код (строки 128-205)
2. Вставить наш HTTP сервер из [main.c](main.c) (функции http_server_run, process_http_request)
3. В главном цикле заменить `MQTTYield` на `http_server_run(HTTP_SOCKET)`

### Шаг 3: Скомпилировать

```bash
cd RP2350-ETH-8DI-8RO/C/02-MQTT
mkdir build && cd build
cmake ..
make
```

### Шаг 4: Загрузить на плату

1. Зажать BOOTSEL
2. Подключить USB
3. Скопировать `build/examples/main.uf2` на диск RPI-RP2

## Требования для компиляции

### Pico SDK

```bash
# Windows
git clone https://github.com/raspberrypi/pico-sdk.git
cd pico-sdk
git submodule update --init
set PICO_SDK_PATH=C:\path\to\pico-sdk

# Linux/Mac
export PICO_SDK_PATH=/path/to/pico-sdk
```

### ARM GCC Toolchain

- Windows: https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm/downloads
- Linux: `sudo apt install gcc-arm-none-eabi`
- Mac: `brew install arm-none-eabi-gcc`

### CMake

```bash
cmake --version  # Должно быть >= 3.13
```

## Конфигурация сети

По умолчанию в [config.h](config.h):
- **IP**: 192.168.1.100
- **Subnet**: 255.255.255.0
- **Gateway**: 192.168.1.1

## API Endpoints

### GET `/`
Главная HTML страница с интерфейсом управления

### GET `/api/relays`
Получить состояние всех реле
```json
{
  "relay_1": {"state": 0},
  "relay_2": {"state": 1},
  ...
}
```

### POST `/api/relay/{id}`
Управление реле (id: 1-8)
```json
{"state": 1}  // 1=ON, 0=OFF
```

### POST `/api/relays/all/on`
Включить все реле

### POST `/api/relays/all/off`
Выключить все реле

## Отладка

Подключите USB кабель и откройте serial терминал (115200 baud) для просмотра логов.

## Известные ограничения

1. HTTP парсер упрощенный - может не работать со всеми клиентами
2. Нет поддержки больших запросов (>2KB)
3. Обрабатывает только один запрос за раз

## Решение проблем

### "W5500 not responding"
- Проверьте SPI подключение
- Проверьте GPIO пины (34,35,36,33,25)
- Убедитесь что на плату подается питание

### "Network timeout"
- Проверьте Ethernet кабель
- Убедитесь что ПК в той же подсети (192.168.1.x)
- Попробуйте пропинговать плату: `ping 192.168.1.100`

### COM порт занят
- Закройте все программы (Thonny, mpremote, serial терминалы)
- Отключите и подключите USB заново

## Лицензия

Основано на примерах Waveshare и WIZnet библиотеках.
