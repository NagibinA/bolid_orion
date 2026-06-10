from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL_STATUS_UPDATE


async def async_setup_entry(hass, entry, async_add_entities):
    status_sensor = OrionStatusSensor()
    async_add_entities([status_sensor])
    hass.data[DOMAIN]["status_sensor"] = status_sensor
    
    async_dispatcher_connect(hass, SIGNAL_STATUS_UPDATE, status_sensor.update_status)


class OrionStatusSensor(SensorEntity):
    def __init__(self):
        self._attr_name = "Bolid Orion Scan Status"
        self._attr_unique_id = f"{DOMAIN}_scan_status"
        self._attr_icon = "mdi:radar"
        self._state = "Ожидание"

    @property
    def native_value(self):
        return self._state

    @callback
    def update_status(self, status: str):
        self._state = status
        self.async_write_ha_state()
