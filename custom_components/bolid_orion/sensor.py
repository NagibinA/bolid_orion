"""Сенсоры для Bolid Orion"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсоров."""
    
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    # Существующие Orion устройства
    for address, info in coordinator.get_orion_devices().items():
        entities.append(OrionDeviceSensor(coordinator, address))
    
    # Существующие DPLS устройства
    for device_key, info in coordinator.get_dpls_devices().items():
        entities.append(DPLSDeviceSensor(coordinator, device_key))
    
    async_add_entities(entities)
    
    # Функция для добавления новых Orion устройств
    @callback
    def add_orion_device(address):
        """Добавление нового Orion устройства."""
        async_add_entities([OrionDeviceSensor(coordinator, address)])
    
    # Функция для добавления новых DPLS устройств
    @callback
    def add_dpls_device(device_key):
        """Добавление нового DPLS устройства."""
        async_add_entities([DPLSDeviceSensor(coordinator, device_key)])
    
    # Функция для обновления статуса DPLS
    @callback
    def update_dpls_status(device_key, status_code, status_text):
        """Обновление статуса DPLS устройства."""
        for entity in hass.data[DOMAIN].get("dpls_entities", []):
            if entity.device_key == device_key:
                entity.update_status(status_code, status_text)
                return
    
    # Сохраняем список сущностей для обновления
    hass.data[DOMAIN]["dpls_entities"] = entities
    
    # Подписываемся на сигналы
    async_dispatcher_connect(hass, f"{DOMAIN}_new_orion_device", add_orion_device)
    async_dispatcher_connect(hass, f"{DOMAIN}_new_dpls_device", add_dpls_device)
    async_dispatcher_connect(hass, f"{DOMAIN}_update_dpls_status", update_dpls_status)


class OrionDeviceSensor(SensorEntity):
    """Сенсор Orion устройства."""
    
    def __init__(self, coordinator, address):
        self.coordinator = coordinator
        self.address = address
        self._attr_unique_id = f"{DOMAIN}_orion_{address}"
        self._attr_should_poll = False
        
        self._update_from_coordinator()
    
    def _update_from_coordinator(self):
        """Обновление данных из координатора."""
        device_info = self.coordinator.get_orion_devices().get(self.address, {})
        self._attr_name = device_info.get("name", "Неизвестный прибор")
        self._attr_native_value = device_info.get("name", "Неизвестный прибор")
        self._attr_extra_state_attributes = {
            "address": self.address,
            "firmware": device_info.get("firmware", "unknown"),
            "type_code": device_info.get("type_code", 0),
        }
    
    async def async_added_to_hass(self):
        """Подписка на обновления координатора."""
        self.coordinator.async_add_listener(self._update_from_coordinator)


class DPLSDeviceSensor(SensorEntity):
    """Сенсор DPLS устройства."""
    
    def __init__(self, coordinator, device_key):
        self.coordinator = coordinator
        self.device_key = device_key
        self._attr_unique_id = f"{DOMAIN}_dpls_{device_key}"
        self._attr_should_poll = False
        
        self._update_from_coordinator()
    
    def _update_from_coordinator(self):
        """Обновление данных из координатора."""
        device_info = self.coordinator.get_dpls_devices().get(self.device_key, {})
        self._attr_name = device_info.get("name", "Неизвестное DPLS устройство")
        self._attr_native_value = device_info.get("name", "Неизвестное DPLS устройство")
        self._attr_extra_state_attributes = {
            "kdl_address": device_info.get("kdl_address"),
            "dpls_address": device_info.get("dpls_address"),
            "type_code": device_info.get("type_code", 0),
            "status_code": device_info.get("status_code"),
            "status_text": device_info.get("status_text"),
        }
    
    async def async_added_to_hass(self):
        """Подписка на обновления координатора."""
        self.coordinator.async_add_listener(self._update_from_coordinator)
    
    @callback
    def update_status(self, status_code, status_text):
        """Обновление статуса (вызывается по сигналу)."""
        self._attr_extra_state_attributes["status_code"] = status_code
        self._attr_extra_state_attributes["status_text"] = status_text
        self.async_write_ha_state()
