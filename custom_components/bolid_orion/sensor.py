from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, DEVICE_TYPES

async def async_setup_entry(hass, entry, async_add_entities):
    """Настройка сенсоров"""
    
    @callback
    def async_add_sensor(address, device_info):
        """Добавление сенсора при обнаружении"""
        entities = []
        entities.append(OrionDeviceSensor(address, device_info))
        async_add_entities(entities)

    # Подписываемся на сигналы о новых устройствах
    async_dispatcher_connect(hass, f"{DOMAIN}_new_device", async_add_sensor)


class OrionDeviceSensor(SensorEntity):
    """Сенсор устройства Orion"""

    def __init__(self, address, device_info):
        self._address = address
        self._device_info = device_info
        self._attr_name = f"Orion Device {address}"
        self._attr_unique_id = f"{DOMAIN}_device_{address}_type"
        self._attr_icon = "mdi:chip"
        
        # Состояние сенсора = название прибора
        self._attr_native_value = device_info.get("name", "Unknown")
        
        # Атрибуты
        self._attr_extra_state_attributes = {
            "address": address,
            "device_type_code": device_info.get("type_code"),
            "firmware": device_info.get("firmware", "unknown"),
            "loops": device_info.get("loops", 0),
            "relays": device_info.get("relays", 0),
        }

    @property
    def should_poll(self):
        return False

    @callback
    def update_device_info(self, device_info):
        """Обновление информации об устройстве"""
        self._device_info = device_info
        self._attr_native_value = device_info.get("name", "Unknown")
        self._attr_extra_state_attributes.update({
            "firmware": device_info.get("firmware", "unknown"),
        })
        self.async_write_ha_state()
