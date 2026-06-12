"""Устройства Bolid Orion Protocol v2.0.0"""

import logging
from datetime import datetime
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, VERSION, ORION_DEVICE_TYPES, DPLS_DEVICE_TYPES

_LOGGER = logging.getLogger(__name__)


class BolidOrionDevice(Entity):
    """Базовое Orion устройство (прямое подключение)"""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Инициализация устройства"""
        self.hass = hass
        self.entry = entry
        self.address = entry.data["address"]
        self.device_type = entry.data["device_type"]
        self.device_name = ORION_DEVICE_TYPES.get(self.device_type, f"Тип {self.device_type}")
        self.custom_name = entry.data.get("name", "")
        
        self._state = "unknown"
        self._firmware = None
        self._last_update = None
        self._attr_should_poll = False
        
        # Уникальный ID
        self._attr_unique_id = f"{DOMAIN}_orion_{self.address}"
        
        # Информация об устройстве
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"orion_{self.address}")},
            name=self.name,
            manufacturer="Bolid",
            model=self.device_name,
            sw_version=VERSION,
            configuration_url=f"orion://{self.address}",
        )
    
    @property
    def name(self):
        """Имя устройства"""
        return self.custom_name or f"{self.device_name} (адрес {self.address})"
    
    @property
    def state(self):
        """Состояние устройства"""
        return self._state
    
    @property
    def extra_state_attributes(self):
        """Дополнительные атрибуты"""
        attrs = {
            "address": self.address,
            "device_type": self.device_type,
            "device_name": self.device_name,
        }
        if self._firmware:
            attrs["firmware"] = self._firmware
        if self._last_update:
            attrs["last_update"] = self._last_update.isoformat()
        return attrs
    
    async def async_update_state(self, new_state: str, firmware: str = None):
        """Обновление состояния устройства"""
        self._state = new_state
        self._last_update = datetime.now()
        if firmware:
            self._firmware = firmware
        self.async_write_ha_state()
        
        # Отправляем сигнал для связанных сущностей
        async_dispatcher_send(self.hass, f"{DOMAIN}_orion_{self.address}_update", new_state)
    
    async def async_update(self):
        """Принудительное обновление (вызывается Home Assistant)"""
        # Будет реализовано в следующей версии
        pass


class BolidDPLSDevice(Entity):
    """DPLS устройство (подключается к КДЛ)"""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Инициализация DPLS устройства"""
        self.hass = hass
        self.entry = entry
        self.kdl_address = entry.data["kdl_address"]
        self.dpls_address = entry.data["dpls_address"]
        self.device_type = entry.data["device_type"]
        self.device_name = DPLS_DEVICE_TYPES.get(self.device_type, f"Тип {self.device_type}")
        self.custom_name = entry.data.get("name", "")
        
        self._state = "unknown"
        self._status_code = None
        self._adc_value = None
        self._last_update = None
        self._attr_should_poll = False
        
        # Уникальный ID
        self._attr_unique_id = f"{DOMAIN}_dpls_{self.kdl_address}_{self.dpls_address}"
        
        # Информация об устройстве (родитель - КДЛ)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"dpls_{self.kdl_address}_{self.dpls_address}")},
            name=self.name,
            manufacturer="Bolid",
            model=self.device_name,
            sw_version=VERSION,
            via_device=(DOMAIN, f"orion_{self.kdl_address}"),
            configuration_url=f"orion://{self.kdl_address}/{self.dpls_address}",
        )
    
    @property
    def name(self):
        """Имя устройства"""
        return self.custom_name or f"{self.device_name} (КДЛ {self.kdl_address}, адрес {self.dpls_address})"
    
    @property
    def state(self):
        """Состояние устройства"""
        return self._state
    
    @property
    def extra_state_attributes(self):
        """Дополнительные атрибуты"""
        attrs = {
            "kdl_address": self.kdl_address,
            "dpls_address": self.dpls_address,
            "device_type": self.device_type,
            "device_name": self.device_name,
        }
        if self._status_code:
            attrs["status_code"] = self._status_code
        if self._adc_value:
            attrs["adc_value"] = self._adc_value
        if self._last_update:
            attrs["last_update"] = self._last_update.isoformat()
        return attrs
    
    async def async_update_state(self, new_state: str, status_code: int = None, adc_value: int = None):
        """Обновление состояния DPLS устройства"""
        self._state = new_state
        self._last_update = datetime.now()
        if status_code is not None:
            self._status_code = status_code
        if adc_value is not None:
            self._adc_value = adc_value
        self.async_write_ha_state()
        
        # Отправляем сигнал для связанных сущностей
        async_dispatcher_send(
            self.hass, 
            f"{DOMAIN}_dpls_{self.kdl_address}_{self.dpls_address}_update", 
            new_state
        )
    
    async def async_update(self):
        """Принудительное обновление (вызывается Home Assistant)"""
        # Будет реализовано в следующей версии
        pass
