"""Config Flow для Bolid Orion Protocol v2.0.0"""

import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, ORION_DEVICE_TYPES, DPLS_DEVICE_TYPES
from .mqtt_client import OrionMQTTClient

_LOGGER = logging.getLogger(__name__)

MQTT_SCHEMA = vol.Schema({
    vol.Required("broker", default="localhost"): str,
    vol.Required("port", default=1883): int,
    vol.Optional("username"): str,
    vol.Optional("password"): str,
})


class BolidOrionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2
    
    async def async_step_user(self, user_input=None):
        errors = {}
        
        if user_input is not None:
            _LOGGER.info("Проверка подключения к MQTT")
            
            mqtt_client = OrionMQTTClient(
                self.hass,
                broker=user_input["broker"],
                port=user_input["port"],
                username=user_input.get("username"),
                password=user_input.get("password")
            )
            
            connected = await mqtt_client.connect()
            await mqtt_client.disconnect()
            
            if connected:
                broker = user_input["broker"]
                title = f"Bolid Orion ({broker})"
                
                return self.async_create_entry(
                    title=title,
                    data={
                        "broker": broker,
                        "port": user_input["port"],
                        "username": user_input.get("username", ""),
                        "password": user_input.get("password", ""),
                        "devices": {},
                    }
                )
            else:
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=MQTT_SCHEMA,
            errors=errors
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Настройки интеграции - добавление устройств"""
    
    def __init__(self, config_entry):
        self._entry = config_entry
        self._selected_kdl = None
    
    async def async_step_init(self, user_input=None):
        """Главное меню"""
        
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_orion":
                return await self.async_step_add_orion()
            elif action == "add_dpls":
                return await self.async_step_select_kdl()
            else:
                return self.async_create_entry(title="", data={})
        
        actions = {
            "add_orion": "Добавить Orion устройство",
            "add_dpls": "Добавить DPLS устройство",
        }
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required("action"): vol.In(actions)})
        )
    
    async def async_step_add_orion(self, user_input=None):
        """Добавление Orion устройства"""
        errors = {}
        
        devices = self._entry.data.get("devices", {})
        used_addresses = self._get_used_orion_addresses(devices)
        free_addresses = [a for a in range(1, 128) if a not in used_addresses]
        
        if not free_addresses:
            return self.async_abort(reason="no_free_addresses")
        
        address_options = {str(addr): f"Адрес {addr}" for addr in free_addresses}
        device_type_options = {str(k): v for k, v in ORION_DEVICE_TYPES.items()}
        
        if user_input is not None:
            try:
                device_type = int(user_input["device_type"])
                address = int(user_input["address"])
                
                device_name = ORION_DEVICE_TYPES.get(device_type, f"Тип {device_type}")
                device_id = f"orion_{address}"
                
                new_device = {
                    "id": device_id,
                    "type": "orion",
                    "address": address,
                    "device_type": device_type,
                    "name": f"{device_name} (адрес {address})",
                }
                
                # Сохраняем в config_entry
                new_devices = dict(devices)
                new_devices[device_id] = new_device
                
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, "devices": new_devices}
                )
                
                # Сохраняем в hass.data для текущей сессии
                if DOMAIN not in self.hass.data:
                    self.hass.data[DOMAIN] = {}
                self.hass.data[DOMAIN]["devices"] = new_devices
                
                # Отправляем сигнал для создания сенсора (БЕЗ ПЕРЕЗАГРУЗКИ)
                async_dispatcher_send(self.hass, f"{DOMAIN}_add_device", new_device)
                
                return self.async_create_entry(title="", data={})
                
            except (ValueError, KeyError) as e:
                _LOGGER.error("Ошибка: %s", e)
                errors["base"] = "invalid_data"
        
        return self.async_show_form(
            step_id="add_orion",
            data_schema=vol.Schema({
                vol.Required("device_type"): vol.In(device_type_options),
                vol.Required("address"): vol.In(address_options),
            }),
            errors=errors
        )
    
    async def async_step_select_kdl(self, user_input=None):
        """Выбор КДЛ для DPLS устройства"""
        
        devices = self._entry.data.get("devices", {})
        kdl_devices = {}
        
        for device_id, device_info in devices.items():
            if device_info.get("type") == "orion" and device_info.get("device_type") == 9:
                kdl_devices[device_id] = device_info.get('name')
        
        if not kdl_devices:
            return self.async_abort(reason="no_kdl_devices")
        
        if user_input is not None:
            self._selected_kdl = user_input["kdl_device_id"]
            return await self.async_step_add_dpls()
        
        return self.async_show_form(
            step_id="select_kdl",
            data_schema=vol.Schema({vol.Required("kdl_device_id"): vol.In(kdl_devices)})
        )
    
    async def async_step_add_dpls(self, user_input=None):
        """Добавление DPLS устройства"""
        errors = {}
        
        devices = self._entry.data.get("devices", {})
        kdl_info = devices.get(self._selected_kdl, {})
        kdl_address = kdl_info.get("address")
        
        used_dpls = self._get_used_dpls_addresses(devices, kdl_address)
        free_addresses = [a for a in range(1, 128) if a not in used_dpls]
        
        if not free_addresses:
            return self.async_abort(reason="no_free_dpls_addresses")
        
        address_options = {str(addr): f"Адрес {addr}" for addr in free_addresses}
        device_type_options = {str(k): v for k, v in DPLS_DEVICE_TYPES.items()}
        
        if user_input is not None:
            try:
                device_type = int(user_input["device_type"])
                dpls_address = int(user_input["dpls_address"])
                
                device_name = DPLS_DEVICE_TYPES.get(device_type, f"Тип {device_type}")
                device_id = f"dpls_{kdl_address}_{dpls_address}"
                
                new_device = {
                    "id": device_id,
                    "type": "dpls",
                    "kdl_address": kdl_address,
                    "dpls_address": dpls_address,
                    "device_type": device_type,
                    "name": f"{device_name} (КДЛ {kdl_address}, адрес {dpls_address})",
                    "parent_device": self._selected_kdl,
                }
                
                new_devices = dict(devices)
                new_devices[device_id] = new_device
                
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, "devices": new_devices}
                )
                
                if DOMAIN not in self.hass.data:
                    self.hass.data[DOMAIN] = {}
                self.hass.data[DOMAIN]["devices"] = new_devices
                
                # Отправляем сигнал для создания сенсора (БЕЗ ПЕРЕЗАГРУЗКИ)
                async_dispatcher_send(self.hass, f"{DOMAIN}_add_device", new_device)
                
                return self.async_create_entry(title="", data={})
                
            except (ValueError, KeyError) as e:
                _LOGGER.error("Ошибка: %s", e)
                errors["base"] = "invalid_data"
        
        return self.async_show_form(
            step_id="add_dpls",
            data_schema=vol.Schema({
                vol.Required("device_type"): vol.In(device_type_options),
                vol.Required("dpls_address"): vol.In(address_options),
            }),
            errors=errors
        )
    
    def _get_used_orion_addresses(self, devices):
        return [d.get("address") for d in devices.values() if d.get("type") == "orion"]
    
    def _get_used_dpls_addresses(self, devices, kdl_address):
        return [d.get("dpls_address") for d in devices.values() 
                if d.get("type") == "dpls" and d.get("kdl_address") == kdl_address]