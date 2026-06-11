"""Сенсоры для Bolid Orion"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсоров"""
    
    entities = []
    
    # Orion устройства
    for address, info in hass.data[DOMAIN].get("orion_devices", {}).items():
        entities.append(OrionDeviceSensor(address, info))
    
    # DPLS устройства
    for device_key, info in hass.data[DOMAIN].get("dpls_devices", {}).items():
        entities.append(DPLSDeviceSensor(device_key, info))
    
    async_add_entities(entities)
    
    @callback
    def add_orion(address, info):
        async_add_entities([OrionDeviceSensor(address, info)])
    
    @callback
    def add_dpls(device_key, info):
        async_add_entities([DPLSDeviceSensor(device_key, info)])
    
    @callback
    def update_dpls_status(device_key, status_code, status_text):
        for entity in entities:
            if isinstance(entity, DPLSDeviceSensor) and entity.device_key == device_key:
                entity.update_status(status_code, status_text)
                return
    
    async_dispatcher_connect(hass, f"{DOMAIN}_new_orion_device", add_orion)
    async_dispatcher_connect(hass, f"{DOMAIN}_new_dpls_device", add_dpls)
    async_dispatcher_connect(hass, f"{DOMAIN}_update_dpls_status", update_dpls_status)


class OrionDeviceSensor(SensorEntity):
    def __init__(self, address, info):
        self.address = address
        self._attr_name = info["name"]
        self._attr_unique_id = f"{DOMAIN}_orion_{address}"
        self._attr_native_value = info["name"]
        self._attr_extra_state_attributes = {
            "address": address,
            "firmware": info.get("firmware", "unknown"),
            "type_code": info.get("type_code", 0),
        }
        self._attr_should_poll = False


class DPLSDeviceSensor(SensorEntity):
    def __init__(self, device_key, info):
        self.device_key = device_key
        self._attr_name = info["name"]
        self._attr_unique_id = f"{DOMAIN}_dpls_{device_key}"
        self._attr_native_value = info["name"]
        self._attr_extra_state_attributes = {
            "kdl_address": info.get("kdl_address"),
            "dpls_address": info.get("dpls_address"),
            "type_code": info.get("type_code", 0),
            "status_code": info.get("status_code"),
            "status_text": info.get("status_text"),
        }
        self._attr_should_poll = False
    
    @callback
    def update_status(self, status_code, status_text):
        self._attr_extra_state_attributes["status_code"] = status_code
        self._attr_extra_state_attributes["status_text"] = status_text
        self.async_write_ha_state()
