"""Сенсоры для Bolid Orion"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

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
        """Добавление нового сенсора"""
        for entity in entities:
            if entity.address == address:
                entity.update_info(device_info)
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
        self._device_name = device_info.get("name", "Неизвестный прибор")
        self._firmware = device_info.get("firmware", "unknown")
        
        # Название сенсора: "С2000-БКИ (адрес 2)"
        self._attr_name = f"{self._device_name} (адрес {address})"
        self._attr_unique_id = f"{DOMAIN}_device_{address}"
        self._attr_icon = "mdi:chip"
        self._attr_native_value = self._device_name
        
        # Атрибуты
        self._attr_extra_state_attributes = {
            "address": address,
            "firmware": self._firmware,
        }

    @property
    def should_poll(self):
        return False

    @callback
    def update_info(self, device_info: dict):
        """Обновление информации об устройстве"""
        self._device_name = device_info.get("name", "Неизвестный прибор")
        self._firmware = device_info.get("firmware", "unknown")
        
        self._attr_name = f"{self._device_name} (адрес {self.address})"
        self._attr_native_value = self._device_name
        self._attr_extra_state_attributes = {
            "address": self.address,
            "firmware": self._firmware,
        }
        self.async_write_ha_state()
