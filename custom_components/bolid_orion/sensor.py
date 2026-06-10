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
    
    for address, info in hass.data[DOMAIN].get("orion_devices", {}).items():
        entities.append(OrionDeviceSensor(address, info))
    
    for device_key, info in hass.data[DOMAIN].get("dpls_devices", {}).items():
        entities.append(DPLSDeviceSensor(device_key, info))
    
    async_add_entities(entities)
    
    @callback
    def add_orion(address, info):
        async_add_entities([OrionDeviceSensor(address, info)])
    
    @callback
    def add_dpls(device_key, info):
        async_add_entities([DPLSDeviceSensor(device_key, info)])
    
    async_dispatcher_connect(hass, f"{DOMAIN}_new_orion_device", add_orion)
    async_dispatcher_connect(hass, f"{DOMAIN}_new_dpls_device", add_dpls)


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
        }
        self._attr_should_poll = False
