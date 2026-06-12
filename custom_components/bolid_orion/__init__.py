"""Интеграция Bolid Orion Protocol v2.0.0"""

import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .mqtt_client import OrionMQTTClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции"""
    
    hass.data.setdefault(DOMAIN, {})
    
    # Восстанавливаем устройства из config_entry
    devices = entry.data.get("devices", {})
    hass.data[DOMAIN]["devices"] = devices
    _LOGGER.info("Загружено устройств из config_entry: %d", len(devices))
    
    # Создаем MQTT клиент
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
        _LOGGER.info("MQTT клиент создан")
    
    # Регистрируем обработчик для добавления новых устройств
    async def handle_add_device(device_info):
        """Обработчик добавления нового устройства"""
        from .sensor import async_add_device
        
        _LOGGER.info("Получен сигнал на добавление устройства: %s", device_info.get("id"))
        await async_add_device(hass, entry, device_info)
    
    async_dispatcher_connect(hass, f"{DOMAIN}_add_device", handle_add_device)
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции - удаляем устройства и сущности"""
    
    # Удаляем все устройства из device_registry
    dev_reg = dr.async_get(hass)
    devices_to_remove = []
    for device in dev_reg.devices.values():
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:
                devices_to_remove.append(device.id)
                break
    
    for device_id in devices_to_remove:
        dev_reg.async_remove_device(device_id)
        _LOGGER.debug("Удалено устройство: %s", device_id)
    
    # Удаляем все сущности из entity_registry
    ent_reg = er.async_get(hass)
    entities_to_remove = []
    for entity in ent_reg.entities.values():
        if entity.config_entry_id == entry.entry_id:
            entities_to_remove.append(entity.entity_id)
    
    for entity_id in entities_to_remove:
        ent_reg.async_remove(entity_id)
        _LOGGER.debug("Удалена сущность: %s", entity_id)
    
    _LOGGER.info("Удалено устройств: %d, сущностей: %d", len(devices_to_remove), len(entities_to_remove))
    
    # Выгружаем платформы
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Очищаем данные
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop("devices", None)
    
    return unload_ok