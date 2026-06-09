"""Сенсор статуса для Bolid Orion"""

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсора статуса"""
    status_sensor = OrionStatusSensor()
    async_add_entities([status_sensor])
    
    # Сохраняем ссылку на сенсор
    hass.data[DOMAIN]["status_sensor"] = status_sensor


class OrionStatusSensor(SensorEntity):
    """Сенсор статуса сканирования"""

    def __init__(self):
        self._attr_name = "Bolid Orion Scan Status"
        self._attr_unique_id = f"{DOMAIN}_scan_status"
        self._attr_icon = "mdi:radar"
        self._state = "Инициализация..."

    @property
    def native_value(self):
        return self._state

    @callback
    def update_status(self, status: str):
        """Обновление статуса"""
        self._state = status
        self.async_write_ha_state()
