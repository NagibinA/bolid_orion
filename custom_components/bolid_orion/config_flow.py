"""Config Flow для Bolid Orion Protocol v2.0.0"""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, ORION_DEVICE_TYPES, DPLS_DEVICE_TYPES

# Схема подключения к MQTT
MQTT_SCHEMA = vol.Schema({
    vol.Required("broker", default="localhost"): str,
    vol.Required("port", default=1883): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Optional("username"): str,
    vol.Optional("password"): str,
})

# Схема для Orion устройства
ORION_SCHEMA = vol.Schema({
    vol.Required("device_type"): selector.Selector(
        {"select": {"options": list(ORION_DEVICE_TYPES.keys()), "mode": "dropdown"}}
    ),
    vol.Required("address", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=127)),
    vol.Optional("name"): str,
})

# Схема для DPLS устройства
DPLS_SCHEMA = vol.Schema({
    vol.Required("device_type"): selector.Selector(
        {"select": {"options": list(DPLS_DEVICE_TYPES.keys()), "mode": "dropdown"}}
    ),
    vol.Required("dpls_address", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=127)),
    vol.Optional("name"): str,
})


class BolidOrionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow для Bolid Orion"""
    
    VERSION = 2
    
    def __init__(self):
        self._mqtt_config = {}
        self._selected_kdl = None
    
    async def async_step_user(self, user_input=None):
        """Шаг 1: Настройка MQTT"""
        errors = {}
        
        if user_input is not None:
            self._mqtt_config = {
                "broker": user_input["broker"],
                "port": user_input["port"],
                "username": user_input.get("username", ""),
                "password": user_input.get("password", ""),
            }
            return await self.async_step_select_category()
        
        return self.async_show_form(
            step_id="user",
            data_schema=MQTT_SCHEMA,
            errors=errors
        )
    
    async def async_step_select_category(self, user_input=None):
        """Шаг 2: Выбор категории устройства"""
        if user_input is not None:
            if user_input["category"] == "orion":
                return await self.async_step_add_orion()
            else:
                return await self.async_step_select_kdl()
        
        return self.async_show_form(
            step_id="select_category",
            data_schema=vol.Schema({
                vol.Required("category"): vol.In({
                    "orion": "Orion устройство (прямое подключение)",
                    "dpls": "DPLS устройство (подключается к КДЛ)"
                })
            })
        )
    
    async def async_step_add_orion(self, user_input=None):
        """Шаг 3a: Добавление Orion устройства"""
        errors = {}
        
        if user_input is not None:
            address = user_input["address"]
            
            # Проверка на дубликат
            for entry in self._async_current_entries():
                if entry.data.get("address") == address and entry.data.get("device_category") == "orion":
                    errors["address"] = "address_already_used"
                    break
            
            if not errors:
                device_type = int(user_input["device_type"])
                device_name = ORION_DEVICE_TYPES.get(device_type, f"Тип {device_type}")
                title = user_input.get("name") or f"{device_name} (адрес {address})"
                
                return self.async_create_entry(
                    title=title,
                    data={
                        **self._mqtt_config,
                        "device_category": "orion",
                        "device_type": device_type,
                        "address": address,
                        "name": user_input.get("name", ""),
                    }
                )
        
        return self.async_show_form(
            step_id="add_orion",
            data_schema=ORION_SCHEMA,
            errors=errors
        )
    
    async def async_step_select_kdl(self, user_input=None):
        """Шаг 3b: Выбор КДЛ для DPLS устройства"""
        
        # Собираем существующие КДЛ устройства
        kdl_devices = {}
        for entry in self._async_current_entries():
            if entry.data.get("device_category") == "orion" and entry.data.get("device_type") == 9:
                addr = entry.data["address"]
                name = entry.data.get("name") or f"КДЛ (адрес {addr})"
                kdl_devices[str(addr)] = name
        
        if not kdl_devices:
            return self.async_abort(reason="no_kdl_devices")
        
        if user_input is not None:
            self._selected_kdl = int(user_input["kdl_address"])
            return await self.async_step_add_dpls()
        
        schema = vol.Schema({
            vol.Required("kdl_address"): vol.In(kdl_devices)
        })
        
        return self.async_show_form(
            step_id="select_kdl",
            data_schema=schema
        )
    
    async def async_step_add_dpls(self, user_input=None):
        """Шаг 3c: Добавление DPLS устройства"""
        errors = {}
        
        if user_input is not None:
            dpls_address = user_input["dpls_address"]
            
            # Проверка на дубликат
            for entry in self._async_current_entries():
                if (entry.data.get("device_category") == "dpls" and 
                    entry.data.get("kdl_address") == self._selected_kdl and
                    entry.data.get("dpls_address") == dpls_address):
                    errors["dpls_address"] = "address_already_used"
                    break
            
            if not errors:
                device_type = int(user_input["device_type"])
                device_name = DPLS_DEVICE_TYPES.get(device_type, f"Тип {device_type}")
                title = user_input.get("name") or f"{device_name} (КДЛ {self._selected_kdl}, адрес {dpls_address})"
                
                return self.async_create_entry(
                    title=title,
                    data={
                        **self._mqtt_config,
                        "device_category": "dpls",
                        "device_type": device_type,
                        "kdl_address": self._selected_kdl,
                        "dpls_address": dpls_address,
                        "name": user_input.get("name", ""),
                    }
                )
        
        return self.async_show_form(
            step_id="add_dpls",
            data_schema=DPLS_SCHEMA,
            errors=errors
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Опции конфигурации"""
        return BolidOrionOptionsFlow(config_entry)


class BolidOrionOptionsFlow(config_entries.OptionsFlow):
    """Настройки устройства"""
    
    def __init__(self, config_entry):
        self.config_entry = config_entry
    
    async def async_step_init(self, user_input=None):
        """Форма настроек"""
        if user_input is not None:
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})
        
        schema = {
            vol.Optional(
                "name",
                default=self.config_entry.data.get("name", "")
            ): str,
            vol.Optional(
                "scan_interval",
                default=self.config_entry.data.get("scan_interval", 30)
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
        }
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema)
        )
