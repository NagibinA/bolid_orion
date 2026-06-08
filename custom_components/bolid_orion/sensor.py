"""Сенсоры для Bolid Orion"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, DEVICE_TYPES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсоров"""
    
    devices = hass.data[DOMAIN].get("devices", {})
    entities = []
    
    for address, device_info in devices.items():
        entities.append(OrionDeviceSensor(address, device_info))
    
    async_add_entities(entities)
    
    @callback
    def async_add_device(address, device_info):
        """Добавление нового сенсора при обнаружении"""
        for entity in entities:
            if entity.address == address:
                entity.update_device_info(device_info)
                return
        new_sensor = OrionDeviceSensor(address, device_info)
        entities.append(new_sensor)
        async_add_entities([new_sensor])
    
    async_dispatcher_connect(hass, f"{DOMAIN}_new_device", async_add_device)


class OrionDeviceSensor(SensorEntity):
    """Сенсор устройства Orion"""

    def __init__(self, address: int, device_info: dict):
        self.address = address
        self._device_info = device_info
        self._attr_name = f"Orion Device {address}"
        self._attr_unique_id = f"{DOMAIN}_device_{address}_type"
        self._attr_icon = "mdi:chip"
        
        # Состояние сенсора = название прибора
        self._attr_native_value = device_info.get("name", "Неизвестный прибор")
    
    @property
    def should_poll(self):
        return False
    
    @callback
    def update_device_info(self, device_info: dict):
        """Обновление информации об устройстве"""
        self._device_info = device_info
        self._attr_native_value = device_info.get("name", "Неизвестный прибор")
        self.async_write_ha_state()
