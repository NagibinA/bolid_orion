"""Интеграция Bolid Orion Protocol"""

import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN
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
    hass.data[DOMAIN]["config"] = entry.data
    
    # Обработчик входящих сообщений
    def handle_message(payload):
        """Обработка сообщения из MQTT"""
        hass.async_create_task(process_message(hass, payload))
    
    # Регистрируем обработчик
    async_dispatcher_connect(hass, f"{DOMAIN}_message", handle_message)
    
    # Загружаем платформу сенсоров
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции"""
    
    # Отключаем MQTT клиент
    mqtt_client = hass.data[DOMAIN].get("mqtt_client")
    if mqtt_client:
        await mqtt_client.disconnect()
    
    # Выгружаем платформы
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    
    return unload_ok


async def process_message(hass: HomeAssistant, payload: str):
    """Обработка входящего сообщения от шлюза"""
    
    _LOGGER.debug(f"Обработка сообщения: {payload}")
    
    # Парсим строку "2 7 0 44 245 0 5 26"
    parts = payload.strip().split()
    if len(parts) < 8:
        _LOGGER.warning(f"Неверный формат: {payload}")
        return
    
    try:
        address = int(parts[0])
        device_type_code = int(parts[3])
        fw_lo = int(parts[4])
        fw_hi = int(parts[5])
        sub_ver = int(parts[6])
        
        # Формируем информацию об устройстве
        from .const import DEVICE_TYPES
        device_name = DEVICE_TYPES.get(device_type_code, f"Неизвестный прибор (код {device_type_code})")
        firmware = f"{fw_hi}.{fw_lo}.{sub_ver}"
        
        device_info = {
            "name": device_name,
            "type_code": device_type_code,
            "firmware": firmware,
            "address": address,
        }
        
        _LOGGER.info(f"Найден прибор: адрес={address}, тип={device_name}, версия={firmware}")
        
        # Проверяем, есть ли уже такое устройство
        devices = hass.data[DOMAIN]["devices"]
        if address not in devices:
            devices[address] = device_info
            # Сигнал для создания сенсора
            async_dispatcher_send(hass, f"{DOMAIN}_new_device", address, device_info)
        else:
            # Обновляем существующее
            if devices[address] != device_info:
                devices[address] = device_info
                # Сигнал для обновления сенсора
                async_dispatcher_send(hass, f"{DOMAIN}_new_device", address, device_info)
                
    except (ValueError, IndexError) as e:
        _LOGGER.error(f"Ошибка парсинга {payload}: {e}")
