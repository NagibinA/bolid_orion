# Bolid Orion Protocol для Home Assistant

Интеграция для работы с устройствами Болид по протоколу Orion через MQTT шлюз.

## Возможности

## Установка через HACS

1. Добавьте репозиторий в HACS:
   - Откройте HACS → Интеграции → ⋮ → Пользовательские репозитории
   - URL: `https://github.com/NagibinA/bolid_orion`
   - Категория: Интеграция

2. Нажмите "Установить"

3. Перезапустите Home Assistant

## Настройка

1. Убедитесь, что MQTT шлюз работает и публикует ответы в топик `WemosOrion/answer`


## Требования

- MQTT брокер
- Шлюз Orion2Mqtt на ESP8266/ESP32


## Лицензия

MIT

## Автор

[NagibinA](https://github.com/NagibinA)
