"""Сенсоры для Bolid Orion"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсоров"""
    
    entities = []
    
    for address, info in hass.data[DOMAIN].get("orion_devices", {}).items():
        entities.append(OrionDeviceSensor(address, info))
    
    for device_key, info in hass.data[DOMAIN].get("dpls_devices", {}).items():
        sensor = DPLSDeviceSensor(device_key, info)
        entities.append(sensor)
        hass.data[DOMAIN]["dpls_entities"].append(sensor)
    
    async_add_entities(entities)
    
    @callback
    def add_orion(address, info):
        async_add_entities([OrionDeviceSensor(address, info)])
    
    @callback
    def add_dpls(device_key, info):
        sensor = DPLSDeviceSensor(device_key, info)
        hass.data[DOMAIN]["dpls_entities"].append(sensor)
        async_add_entities([sensor])
    
    @callback
    def update_dpls_status(device_key, status_code, status_text):
        for entity in hass.data[DOMAIN].get("dpls_entities", []):
            if entity.device_key == device_key:
                entity.update_status(status_code, status_text)
                return
    
    @callback
    def update_dpls_adc(device_key, adc_value):
        for entity in hass.data[DOMAIN].get("dpls_entities", []):
            if entity.device_key == device_key:
                entity.update_adc(adc_value)
                return
    
    async_dispatcher_connect(hass, f"{DOMAIN}_new_orion_device", add_orion)
    async_dispatcher_connect(hass, f"{DOMAIN}_new_dpls_device", add_dpls)
    async_dispatcher_connect(hass, f"{DOMAIN}_update_dpls_status", update_dpls_status)
    async_dispatcher_connect(hass, f"{DOMAIN}_update_dpls_adc", update_dpls_adc)


class OrionDeviceSensor(SensorEntity):
    def __init__(self, address, info):
        self.address = address
        self._attr_name = info["name"]
        self._attr_unique_id = slugify(f"{DOMAIN}_orion_{address}")
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
        self._attr_unique_id = slugify(f"{DOMAIN}_dpls_{device_key}")
        
        status_text = info.get("status_text")
        if status_text:
            self._attr_native_value = status_text
        else:
            self._attr_native_value = info["name"]
        
        self._attr_extra_state_attributes = {
            "device_name": info["name"],
            "kdl_address": info.get("kdl_address"),
            "dpls_address": info.get("dpls_address"),
            "type_code": info.get("type_code", 0),
            "status_code": info.get("status_code"),
            "adc_value": info.get("adc_value"),
        }
        self._attr_should_poll = False
    
    @callback
    def update_status(self, status_code, status_text):
        self._attr_extra_state_attributes["status_code"] = status_code
        self._attr_native_value = status_text
        self.async_write_ha_state()
    
    @callback
    def update_adc(self, adc_value):
        self._attr_extra_state_attributes["adc_value"] = adc_value
        self.async_write_ha_state()
