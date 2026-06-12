"""Интеграция Bolid Orion Protocol v2.0.0"""

import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .mqtt_client import OrionMQTTClient
from .device import BolidOrionDevice, BolidDPLSDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции из config entry"""
    
    # Инициализация данных
    hass.data.setdefault(DOMAIN, {})
    
    # Создаем MQTT клиент (один на всю интеграцию)
    if "mqtt_client" not in hass.data[DOMAIN]:
        mqtt_client = OrionMQTTClient(
            hass,
            broker=entry.data["broker"],
            port=entry.data["port"],
            username=entry.data.get("username"),
            password=entry.data.get("password")
        )
        connected = await mqtt_client.connect()
        if not connected:
            _LOGGER.error("Не удалось подключиться к MQTT брокеру")
            return False
        hass.data[DOMAIN]["mqtt_client"] = mqtt_client
        _LOGGER.info("MQTT клиент создан и подключен")
    
    # Создаем устройство в зависимости от типа
    if entry.data.get("device_category") == "orion":
        device = BolidOrionDevice(hass, entry)
    else:
        device = BolidDPLSDevice(hass, entry)
    
    # Сохраняем устройство
    hass.data[DOMAIN][entry.entry_id] = {
        "device": device,
        "entry_id": entry.entry_id,
    }
    
    # Регистрируем платформы
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("Устройство %s успешно настроено", device.name)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции"""
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Устройство %s выгружено", entry.title)
    
    # Если не осталось устройств, отключаем MQTT клиент
    if not hass.data[DOMAIN]:
        mqtt_client = hass.data[DOMAIN].get("mqtt_client")
        if mqtt_client:
            await mqtt_client.disconnect()
        hass.data.pop(DOMAIN, None)
        _LOGGER.info("MQTT клиент отключен")
    
    return unload_ok
