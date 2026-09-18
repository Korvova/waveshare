**Unirack-1** — блок управления питанием и мониторинга стойки на базе платы Waveshare RP2350-Relay: 8 реле (4 розетки, 2 блока питания, вентиляторы, выход на контактор), 6 цифровых входов (двери, сброс), датчики температуры/влажности (DS18B20 ×3, DHT22), измеритель электропитания PZEM-004T, Ethernet (W5500). Прошивка на MicroPython: встроенный веб-интерфейс + MQTT.

Партия из **12 устройств** прошита и отгружена заказчику 10.07.2026.

## Состояние

- ✅ 10.07.2026 — все 12 устройств прошиты, проверены, отгружены; документация (инструкция, клеммник, чек-лист, MQTT) в комплекте
- ⌛ 18.09.2026 — рекламация заказчика: у всех устройств был одинаковый MAC-адрес (зашит константой). Фикс готов и в git (коммит `9aca0d6`): MAC и MQTT Client ID теперь уникальные из ID чипа. Заказчику отправлен пакет самостоятельного обновления `Unirack-1-update-MAC.zip` — **ждём подтверждения обновления устройств**
- ⬜ Следующая ревизия прошивки: MQTT LWT (авто-offline при обрыве связи)

## Код и доступы

- GitHub: **https://github.com/Korvova/waveshare** — актуальная прошивка в папке **`MQTT-2-0`** (main.py + w5500_simple.py). Папка `w5500_lib` — прежняя итерация, для новых работ не использовать
- IP устройства по умолчанию: `192.168.1.100` (у всех с завода одинаковый — в одну сеть подключать по одному и сразу менять)
- Веб-интерфейс: `http://<ip>/`; MQTT base topic по умолчанию `unirack1`, брокер задаётся в вебке
- Прошивка/обновление: по USB (кабель за передней панелью без разъёмов), порт определяется автоматически (VID 2E8A) — см. [Прошивка и обновление устройств](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/proshivka-i-obnovlenie)
- MAC после обновления: `02:08:DC:xx:xx:xx`, уникальный, показан в вебке рядом с Board IP

## Оглавление

- [Т. Прошивка Unirack-1](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/t-proshivka) — требования заказчика, статусы, уроки
- [Инструкция пользователя](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/instrukcija) — подключение, реле, двери, датчики, сеть, MQTT
- [Контакты (клеммник)](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/kontakty) — листик с названиями всех клемм
- [Чек-лист приёмки](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/chek-list) — 11 пунктов проверки устройства
- [Протокол MQTT](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/protokol-mqtt) — полная спецификация: топики, JSON, интеграции
- [Прошивка и обновление устройств](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/proshivka-i-obnovlenie) — как шить новые платы и обновлять у заказчика

Источник правды — репозиторий: страницы публикуются скриптом `tools/wiki_publish.py`, пользовательские документы берутся из `MQTT-2-0/*.md` (одни и те же файлы идут в PDF для заказчика и в вики).

## Железо (заметки)

PZEM-004T (измеритель тока/напряжения) подключён на **TX: GPIO40, RX: GPIO43**; датчики: DS18B20 — GPIO41 (1-Wire), DHT22 — GPIO42. Полная раскладка — в [клеммнике](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/kontakty).

![2026-03-16](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/.files/2026-03-1611-47-59.png =483x260)

![2026-04-28_15-09-02.png](/homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack/.files/2026-04-2815-09-02.png =630x600)
