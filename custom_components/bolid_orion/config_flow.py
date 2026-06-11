"""Config Flow для Bolid Orion"""

import asyncio
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN

DATA_SCHEMA = vol.Schema({
    vol.Required("broker"): str,
    vol.Required("port", default=1883): int,
    vol.Optional("username"): str,
    vol.Optional("password"): str,
})


class BolidOrionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=f"Bolid Orion ({user_input['broker']})",
                data=user_input
            )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BolidOrionOptionsFlow(config_entry)


class BolidOrionOptionsFlow(config_entries.OptionsFlow):
    """Options Flow для управления адресами"""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.device_type = None
        self.selected_device = None
        self.free_addresses = []

    async def async_step_init(self, user_input=None):
        """Главное меню опций"""
        
        if user_input is not None:
            if user_input.get("action") == "change_orion_address":
                return await self.async_step_select_orion_device()
            elif user_input.get("action") == "change_dpls_address":
                return await self.async_step_select_dpls_device()
            elif user_input.get("action") == "refresh_free_addresses":
                await self._refresh_free_addresses()
                return await self.async_step_init()
        
        orion_devices = self.hass.data[DOMAIN].get("orion_devices", {})
        dpls_devices = self.hass.data[DOMAIN].get("dpls_devices", {})
        
        used_orion = list(orion_devices.keys())
        used_dpls = [info.get("dpls_address") for info in dpls_devices.values() if info.get("dpls_address")]
        
        data_schema = vol.Schema({
            vol.Required("action"): vol.In({
                "change_orion_address": f"Сменить адрес Orion устройства (заняты: {used_orion})",
                "change_dpls_address": f"Сменить адрес DPLS устройства (заняты: {used_dpls})",
                "refresh_free_addresses": "Обновить список свободных адресов"
            })
        })
        
        return self.async_show_form(step_id="init", data_schema=data_schema)
    
    async def async_step_select_orion_device(self, user_input=None):
        """Выбор Orion устройства"""
        
        orion_devices = self.hass.data[DOMAIN].get("orion_devices", {})
        
        if user_input is not None:
            self.device_type = "orion"
            self.selected_device = user_input["device"]
            return await self.async_step_select_new_address()
        
        devices_list = {
            str(addr): f"Адрес {addr}: {info['name']}" 
            for addr, info in orion_devices.items()
        }
        
        data_schema = vol.Schema({
            vol.Required("device"): vol.In(devices_list)
        })
        
        return self.async_show_form(step_id="select_orion_device", data_schema=data_schema)
    
    async def async_step_select_dpls_device(self, user_input=None):
        """Выбор DPLS устройства"""
        
        dpls_devices = self.hass.data[DOMAIN].get("dpls_devices", {})
        
        if user_input is not None:
            self.device_type = "dpls"
            self.selected_device = user_input["device"]
            return await self.async_step_select_new_address()
        
        devices_list = {}
        for key, info in dpls_devices.items():
            kdl = info.get("kdl_address")
            dpls = info.get("dpls_address")
            name = info.get("name")
            devices_list[key] = f"КДЛ {kdl}, DPLS {dpls}: {name}"
        
        data_schema = vol.Schema({
            vol.Required("device"): vol.In(devices_list)
        })
        
        return self.async_show_form(step_id="select_dpls_device", data_schema=data_schema)
    
    async def async_step_select_new_address(self, user_input=None):
        """Выбор нового адреса"""
        
        if user_input is not None:
            new_address = int(user_input["new_address"])
            mqtt_client = self.hass.data[DOMAIN].get("mqtt_client")
            
            if self.device_type == "orion":
                old_addr = int(self.selected_device)
                command = f"{old_addr};6;0;15;{new_address};{new_address}"
                await mqtt_client.send_command(command)
                await asyncio.sleep(2)
                await self._update_orion_device(old_addr, new_address)
            else:
                parts = self.selected_device.split("_")
                kdl_addr = int(parts[0])
                old_addr = int(parts[1])
                command = f"{kdl_addr};7;0;39;6;{old_addr};{new_address}"
                await mqtt_client.send_command(command)
                await asyncio.sleep(2)
                await self._update_dpls_device(kdl_addr, old_addr, new_address)
            
            return self.async_create_entry(title="", data={})
        
        await self._refresh_free_addresses()
        current_addr = self._get_current_address()
        available = [str(a) for a in self.free_addresses if a != current_addr]
        
        if not available:
            return self.async_abort(reason="no_free_addresses")
        
        data_schema = vol.Schema({
            vol.Required("new_address"): vol.In(available)
        })
        
        return self.async_show_form(step_id="select_new_address", data_schema=data_schema)
    
    async def _refresh_free_addresses(self):
        """Обновление списка свободных адресов"""
        orion_devices = self.hass.data[DOMAIN].get("orion_devices", {})
        dpls_devices = self.hass.data[DOMAIN].get("dpls_devices", {})
        
        used_orion = set(orion_devices.keys())
        used_dpls = set()
        for info in dpls_devices.values():
            if info.get("dpls_address"):
                used_dpls.add(info.get("dpls_address"))
        
        all_used = used_orion | used_dpls
        self.free_addresses = [a for a in range(1, 128) if a not in all_used]
    
    def _get_current_address(self):
        if self.device_type == "orion":
            return int(self.selected_device)
        else:
            parts = self.selected_device.split("_")
            return int(parts[1])
    
    async def _update_orion_device(self, old_addr, new_addr):
        """Обновление Orion устройства"""
        devices = self.hass.data[DOMAIN]["orion_devices"]
        device_info = devices.pop(old_addr, None)
        if device_info:
            device_info["address"] = new_addr
            devices[new_addr] = device_info
            
            ent_reg = er.async_get(self.hass)
            old_entity_id = f"sensor.{DOMAIN}_orion_{old_addr}"
            entity = ent_reg.async_get(old_entity_id)
            if entity:
                ent_reg.async_update_entity(
                    entity.entity_id,
                    new_unique_id=f"{DOMAIN}_orion_{new_addr}",
                )
    
    async def _update_dpls_device(self, kdl_addr, old_addr, new_addr):
        """Обновление DPLS устройства"""
        old_key = f"{kdl_addr}_{old_addr}"
        new_key = f"{kdl_addr}_{new_addr}"
        
        devices = self.hass.data[DOMAIN]["dpls_devices"]
        device_info = devices.pop(old_key, None)
        if device_info:
            device_info["dpls_address"] = new_addr
            devices[new_key] = device_info
            
            ent_reg = er.async_get(self.hass)
            old_entity_id = f"sensor.{DOMAIN}_dpls_{old_key}"
            entity = ent_reg.async_get(old_entity_id)
            if entity:
                ent_reg.async_update_entity(
                    entity.entity_id,
                    new_unique_id=f"{DOMAIN}_dpls_{new_key}",
                )
