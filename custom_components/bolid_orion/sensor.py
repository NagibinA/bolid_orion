"""Сенсоры для Bolid Orion Protocol v2.0.0"""

import logging
import asyncio
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, ORION_DEVICE_TYPES, DPLS_DEVICE_TYPES, RSP_ORION

_LOGGER = logging.getLogger(__name__)


# Глобальная переменная для хранения функции добавления сенсоров
_add_entities_func = None
_hass_instance = None
_entry_instance = None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    """Настройка сенсоров"""
    global _add_entities_func, _hass_instance, _entry_instance
    
    _add_entities_func = async_add_entities
    _hass_instance = hass
    _entry_instance = entry
    
    devices = hass.data.get(DOMAIN, {}).get("devices", {})
    mqtt_client = hass.data.get(DOMAIN, {}).get("mqtt_client")
    entities = []
    
    _LOGGER.info("Настройка сенсоров для %d устройств", len(devices))
    
    for device_id, device_info in devices.items():
        if device_info.get("type") == "orion":
            sensor = OrionDeviceSensor(device_id, device_info, entry)
            entities.append(sensor)
        elif device_info.get("type") == "dpls":
            sensor = DPLSDeviceSensor(device_id, device_info, entry)
            entities.append(sensor)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Добавлено %d сенсоров", len(entities))
        
        # Один опрос при создании (только для Orion)
        if mqtt_client:
            for sensor in entities:
                if isinstance(sensor, OrionDeviceSensor):
                    await sensor.async_poll(mqtt_client)
                    await asyncio.sleep(1)


async def async_add_device(hass: HomeAssistant, entry: ConfigEntry, device_info: dict):
    """Динамическое добавление нового сенсора (без перезагрузки платформы)"""
    global _add_entities_func
    
    if not _add_entities_func:
        _LOGGER.error("Функция добавления сенсоров не инициализирована")
        return
    
    mqtt_client = hass.data.get(DOMAIN, {}).get("mqtt_client")
    
    if device_info.get("type") == "orion":
        sensor = OrionDeviceSensor(device_info["id"], device_info, entry)
        _add_entities_func([sensor])
        _LOGGER.info("Динамически добавлен Orion сенсор: %s", device_info.get("name"))
        
        # Опрашиваем только новое устройство
        if mqtt_client:
            await sensor.async_poll(mqtt_client)
            
    elif device_info.get("type") == "dpls":
        sensor = DPLSDeviceSensor(device_info["id"], device_info, entry)
        _add_entities_func([sensor])
        _LOGGER.info("Динамически добавлен DPLS сенсор: %s", device_info.get("name"))


class OrionDeviceSensor(SensorEntity):
    """Сенсор Orion устройства"""
    
    def __init__(self, device_id: str, device_info: dict, entry):
        self.device_id = device_id
        self.entry = entry
        self.address = device_info["address"]
        self.device_type = device_info["device_type"]
        self.device_name = ORION_DEVICE_TYPES.get(self.device_type, "Unknown")
        
        self._attr_name = device_info.get("name")
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_native_value = "Опрос..."
        self._attr_icon = "mdi:chip"
        self._attr_should_poll = False
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._attr_name,
            manufacturer="Bolid",
            model=self.device_name,
        )
    
    @property
    def extra_state_attributes(self):
        return {
            "address": self.address,
            "device_type": self.device_type,
            "device_name": self.device_name,
        }
    
    async def async_poll(self, mqtt_client):
        """Один опрос устройства при создании"""
        command = f"{self.address};6;0;13;0;0"
        _LOGGER.debug("Опрос Orion устройства %s: %s", self.address, command)
        
        try:
            response = await mqtt_client.send_command_and_wait(command, expected_type=RSP_ORION, timeout=10.0)
            
            if response:
                parts = response.strip().split()
                if len(parts) >= 8:
                    try:
                        byte4 = int(parts[4])
                        byte5 = int(parts[5])
                        devVer = byte4 | (byte5 << 8)
                        major = devVer // 100
                        minor = devVer % 100
                        firmware = f"{major}.{minor:02d}"
                        self._attr_native_value = f"Версия {firmware}"
                        
                        self._attr_device_info = DeviceInfo(
                            identifiers={(DOMAIN, self.device_id)},
                            name=self._attr_name,
                            manufacturer="Bolid",
                            model=self.device_name,
                            sw_version=firmware,
                        )
                        _LOGGER.info("Устройство %s ответило, версия: %s", self.address, firmware)
                    except (ValueError, IndexError):
                        self._attr_native_value = "Online"
                else:
                    self._attr_native_value = "Online"
            else:
                self._attr_native_value = "Нет ответа"
                _LOGGER.warning("Нет ответа от устройства %s", self.address)
        except Exception as e:
            _LOGGER.error("Ошибка опроса %s: %s", self.address, e)
            self._attr_native_value = "Ошибка"
        
        self.async_write_ha_state()


class DPLSDeviceSensor(SensorEntity):
    """Сенсор DPLS устройства"""
    
    def __init__(self, device_id: str, device_info: dict, entry):
        self.device_id = device_id
        self.entry = entry
        self.kdl_address = device_info["kdl_address"]
        self.dpls_address = device_info["dpls_address"]
        self.device_type = device_info["device_type"]
        self.device_name = DPLS_DEVICE_TYPES.get(self.device_type, "Unknown")
        
        self._attr_name = device_info.get("name")
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_native_value = "Ожидание"
        self._attr_icon = "mdi:chip"
        self._attr_should_poll = False
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._attr_name,
            manufacturer="Bolid",
            model=self.device_name,
            via_device=(DOMAIN, device_info.get("parent_device", "gateway")),
        )
    
    @property
    def extra_state_attributes(self):
        return {
            "kdl_address": self.kdl_address,
            "dpls_address": self.dpls_address,
            "device_type": self.device_type,
            "device_name": self.device_name,
        }