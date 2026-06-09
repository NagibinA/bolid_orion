"""Интеграция Bolid Orion Protocol"""

import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .const import DOMAIN, DEVICE_TYPES
from .mqtt_client import OrionMQTTClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции из Config Entry"""
    
    # Создаём MQTT клиент
    mqtt_client = OrionMQTTClient(hass, entry.data)
    await mqtt_client.connect()
    
    # Сохраняем в hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["mqtt_client"] = mqtt_client
    hass.data[DOMAIN]["devices"] = {}
    hass.data[DOMAIN]["discovered"] = set()
    
    # Обработчик входящих сообщений
    def handle_message(payload):
        """Обработка сообщения из MQTT (вызывается из потока)"""
        hass.create_task(process_message(hass, payload))
    
    async_dispatcher_connect(hass, f"{DOMAIN}_message", handle_message)
    
    # Загружаем платформы сенсоров
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])
    
    # Запускаем сканирование адресов
    hass.create_task(scan_devices(hass))
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции"""
    
    mqtt_client = hass.data[DOMAIN].get("mqtt_client")
    if mqtt_client:
        await mqtt_client.disconnect()
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])
    
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    
    return unload_ok


async def scan_devices(hass: HomeAssistant):
    """Сканирование адресов 1-127"""
    
    mqtt_client = hass.data[DOMAIN]["mqtt_client"]
    status_sensor = hass.data[DOMAIN].get("status_sensor")
    
    # Обновляем статус
    if status_sensor:
        status_sensor.update_status("Сканирование: подготовка...")
    
    # Небольшая задержка перед началом
    await asyncio.sleep(2)
    
    for addr in range(1, 128):
        # Обновляем статус
        if status_sensor:
            status_sensor.update_status(f"Сканирование: адрес {addr} из 127")
        
        # Отправляем команду
        command = f"{addr};6;0;13;0;0"
        await mqtt_client.send_command(command)
        
        # Ждём ответ 300 мс
        await asyncio.sleep(0.3)
    
    found_count = len(hass.data[DOMAIN]["devices"])
    
    if status_sensor:
        if found_count == 0:
            status_sensor.update_status("Завершено. Устройства не найдены")
        else:
            status_sensor.update_status(f"Завершено. Найдено устройств: {found_count}")
    
    _LOGGER.info(f"Сканирование завершено. Найдено устройств: {found_count}")


async def process_message(hass: HomeAssistant, payload: str):
    """Обработка входящего сообщения от шлюза"""
    
    parts = payload.strip().split()
    if len(parts) < 8:
        return
    
    # Проверяем, что это ответ на запрос типа (байт 2 == 0)
    if int(parts[2]) != 0:
        return
    
    address = int(parts[0])
    sz = int(parts[1])           # длина пакета
    device_type = int(parts[3])
    
    # === ПРАВИЛЬНОЕ ОПРЕДЕЛЕНИЕ ВЕРСИИ ===
    # Как в вашем коде: devVer = buff[4] | (buff[5] << 8)
    byte4 = int(parts[4])
    byte5 = int(parts[5]) if len(parts) > 5 else 0
    
    devVer = byte4 | (byte5 << 8)
    major = devVer // 100
    minor = devVer % 100
    
    if minor < 10:
        version = f"{major}.0{minor}"
    else:
        version = f"{major}.{minor}"
    
    device_name = DEVICE_TYPES.get(device_type, f"Неизвестный тип {device_type}")
    
    _LOGGER.info(f"Найден прибор: адрес={address}, тип={device_name}, версия={version}")
    
    devices = hass.data[DOMAIN]["devices"]
    discovered = hass.data[DOMAIN]["discovered"]
    
    device_info = {
        "name": device_name,
        "type": device_type,
        "firmware": version,
    }
    
    if address not in discovered:
        discovered.add(address)
        devices[address] = device_info
        async_dispatcher_send(hass, f"{DOMAIN}_new_device", address, device_info)
