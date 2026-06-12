"""Сенсоры для Bolid Orion Protocol v2.0.0"""

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    """Настройка сенсоров для интеграции"""
    
    device_data = hass.data[DOMAIN].get(entry.entry_id)
    if not device_data:
        _LOGGER.error("Устройство не найдено для entry %s", entry.entry_id)
        return
    
    device = device_data["device"]
    
    # Создаем сенсор статуса
    status_sensor = OrionStatusSensor(device)
    async_add_entities([status_sensor])
    
    _LOGGER.debug("Создан сенсор статуса для %s", device.name)


class OrionStatusSensor(SensorEntity):
    """Сенсор статуса Orion/DPLS устройства"""
    
    def __init__(self, device):
        """Инициализация сенсора"""
        self.device = device
        self._attr_name = f"{device.name} Статус"
        self._attr_unique_id = f"{device.unique_id}_status"
        self._attr_device_info = device.device_info
        self._attr_icon = "mdi:chip"
        self._attr_should_poll = False
        self._attr_native_value = device.state
        
        # Определяем тип устройства для сигнала
        if hasattr(device, 'address'):  # Orion устройство
            self._signal = f"{DOMAIN}_orion_{device.address}_update"
        else:  # DPLS устройство
            self._signal = f"{DOMAIN}_dpls_{device.kdl_address}_{device.dpls_address}_update"
    
    @property
    def native_value(self):
        """Текущее значение сенсора"""
        return self._attr_native_value
    
    @property
    def extra_state_attributes(self):
        """Дополнительные атрибуты"""
        return self.device.extra_state_attributes
    
    async def async_added_to_hass(self):
        """Подписка на обновления устройства"""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._signal,
                self._handle_update
            )
        )
    
    @callback
    def _handle_update(self, state: str):
        """Обновление состояния сенсора"""
        self._attr_native_value = state
        self.async_write_ha_state()
