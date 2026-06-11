"""Config Flow для Bolid Orion"""

import asyncio
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

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
        return BolidOrionOptionsFlow()


class BolidOrionOptionsFlow(config_entries.OptionsFlow):
    """Options Flow для управления адресами"""

    def __init__(self) -> None:
        self.device_type = None
        self.selected_device = None
        self.free_addresses = []

    async def async_step_init(self, user_input=None):
        """Главное меню опций"""
        
        if user_input is not None:
            action = user_input.get("action")
            if action == "change_orion_address":
                return await self.async_step_select_orion_device()
            elif action == "change_dpls_address":
                return await self.async_step_select_dpls_device()
            elif action == "refresh_free_addresses":
                await self._refresh_free_addresses()
                return await self.async_step_init()
            elif action == "rescan_orion":
                return await self.async_step_rescan_orion()
            elif action == "rescan_dpls":
                return await self.async_step_select_kdl_for_rescan()
        
        orion_devices = self.hass.data.get(DOMAIN, {}).get("orion_devices", {})
        dpls_devices = self.hass.data.get(DOMAIN, {}).get("dpls_devices", {})
        
        used_orion = list(orion_devices.keys())
        used_dpls = [info.get("dpls_address") for info in dpls_devices.values() if info.get("dpls_address")]
        
        schema = vol.Schema({
            vol.Required("action"): vol.In({
                "change_orion_address": f"Сменить адрес Orion (заняты: {used_orion})",
                "change_dpls_address": f"Сменить адрес DPLS (заняты: {used_dpls})",
                "rescan_orion": "Пересканировать Orion",
                "rescan_dpls": "Пересканировать DPLS",
                "refresh_free_addresses": "Обновить список свободных адресов"
            })
        })
        
        return self.async_show_form(step_id="init", data_schema=schema)
    
    async def async_step_rescan_orion(self, user_input=None):
        """Пересканирование Orion"""
        from . import scan_orion_devices
        mqtt_client = self.hass.data.get(DOMAIN, {}).get("mqtt_client")
        if mqtt_client:
            self.hass.async_create_task(scan_orion_devices(self.hass, mqtt_client))
        return self.async_create_entry(title="", data={})
    
    async def async_step_select_kdl_for_rescan(self, user_input=None):
        """Выбор КДЛ для пересканирования DPLS"""
        from . import scan_dpls_line
        
        if user_input is not None:
            kdl_addr = int(user_input["kdl_address"])
            mqtt_client = self.hass.data.get(DOMAIN, {}).get("mqtt_client")
            if mqtt_client:
                self.hass.async_create_task(scan_dpls_line(self.hass, mqtt_client, kdl_addr))
            return self.async_create_entry(title="", data={})
        
        orion_devices = self.hass.data.get(DOMAIN, {}).get("orion_devices", {})
        kdl_list = {}
        for addr, info in orion_devices.items():
            if info.get("type_code") == 9:
                kdl_list[str(addr)] = f"КДЛ адрес {addr}"
        
        if not kdl_list:
            return self.async_abort(reason="no_kdl_found")
        
        schema = vol.Schema({
            vol.Required("kdl_address"): vol.In(kdl_list)
        })
        return self.async_show_form(step_id="select_kdl_for_rescan", data_schema=schema)
    
    async def async_step_select_orion_device(self, user_input=None):
        """Выбор Orion устройства"""
        
        orion_devices = self.hass.data.get(DOMAIN, {}).get("orion_devices", {})
        
        if user_input is not None:
            self.device_type = "orion"
            self.selected_device = user_input["device"]
            return await self.async_step_select_new_address()
        
        devices_list = {
            str(addr): f"Адрес {addr}: {info['name']}" 
            for addr, info in orion_devices.items()
        }
        
        schema = vol.Schema({
            vol.Required("device"): vol.In(devices_list)
        })
        
        return self.async_show_form(step_id="select_orion_device", data_schema=schema)
    
    async def async_step_select_dpls_device(self, user_input=None):
        """Выбор DPLS устройства"""
        
        dpls_devices = self.hass.data.get(DOMAIN, {}).get("dpls_devices", {})
        
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
        
        schema = vol.Schema({
            vol.Required("device"): vol.In(devices_list)
        })
        
        return self.async_show_form(step_id="select_dpls_device", data_schema=schema)
    
    async def async_step_select_new_address(self, user_input=None):
        """Выбор нового адреса"""
        
        if user_input is not None:
            new_address = int(user_input["new_address"])
            mqtt_client = self.hass.data.get(DOMAIN, {}).get("mqtt_client")
            
            if mqtt_client:
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
        
        schema = vol.Schema({
            vol.Required("new_address"): vol.In(available)
        })
        
        return self.async_show_form(step_id="select_new_address", data_schema=schema)
    
    async def _refresh_free_addresses(self):
        """Обновление списка свободных адресов"""
        orion_devices = self.hass.data.get(DOMAIN, {}).get("orion_devices", {})
        dpls_devices = self.hass.data.get(DOMAIN, {}).get("dpls_devices", {})
        
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
        """Обновление Orion устройства после смены адреса (с удалением связанных DPLS)"""
        
        orion_devices = self.hass.data.get(DOMAIN, {}).get("orion_devices", {})
        kdl_addresses = self.hass.data.get(DOMAIN, {}).get("kdl_addresses", [])
        dpls_devices = self.hass.data.get(DOMAIN, {}).get("dpls_devices", {})
        dpls_entities = self.hass.data.get(DOMAIN, {}).get("dpls_entities", [])
        
        device_info = orion_devices.pop(old_addr, None)
        
        if not device_info:
            _LOGGER.error(f"Устройство с адресом {old_addr} не найдено")
            return
        
        is_kdl = (device_info.get("type_code") == 9)
        
        # Обновляем адрес в информации об устройстве
        device_info["address"] = new_addr
        orion_devices[new_addr] = device_info
        
        # Получаем entity registry
        ent_reg = er.async_get(self.hass)
        
        # 1. Удаляем старый сенсор Orion
        old_entity_id = f"sensor.{DOMAIN}_orion_{old_addr}"
        old_entity = ent_reg.async_get(old_entity_id)
        if old_entity:
            ent_reg.async_remove(old_entity.entity_id)
            _LOGGER.info(f"Удалён старый сенсор Orion с адресом {old_addr}")
        
        # 2. Если это КДЛ — удаляем все его DPLS устройства
        if is_kdl:
            _LOGGER.info(f"КДЛ {old_addr} меняет адрес на {new_addr}. Удаляем все связанные DPLS устройства...")
            
            # Находим все DPLS устройства этого КДЛ
            devices_to_remove = []
            for key, info in dpls_devices.items():
                if info.get("kdl_address") == old_addr:
                    devices_to_remove.append(key)
            
            # Удаляем каждое устройство
            for key in devices_to_remove:
                # Удаляем из entity registry
                entity_id = f"sensor.{DOMAIN}_dpls_{key}"
                entity = ent_reg.async_get(entity_id)
                if entity:
                    ent_reg.async_remove(entity.entity_id)
                    _LOGGER.info(f"Удалён DPLS сенсор {key}")
                
                # Удаляем из dpls_devices
                dpls_devices.pop(key, None)
                
                # Удаляем из dpls_entities
                for entity_obj in dpls_entities[:]:
                    if hasattr(entity_obj, 'device_key') and entity_obj.device_key == key:
                        dpls_entities.remove(entity_obj)
                        break
            
            _LOGGER.info(f"Удалено {len(devices_to_remove)} DPLS устройств")
            
            # Обновляем список КДЛ адресов
            if old_addr in kdl_addresses:
                kdl_addresses.remove(old_addr)
                kdl_addresses.append(new_addr)
                _LOGGER.info(f"Обновлён адрес КДЛ: {old_addr} -> {new_addr}")
            
            # 3. Пересканируем DPLS линию через новый адрес КДЛ
            from . import scan_dpls_line
            mqtt_client = self.hass.data.get(DOMAIN, {}).get("mqtt_client")
            if mqtt_client:
                _LOGGER.info(f"Запуск сканирования DPLS для нового КДЛ с адресом {new_addr}")
                self.hass.async_create_task(scan_dpls_line(self.hass, mqtt_client, new_addr))
        
        # 4. Создаём новый сенсор Orion
        async_dispatcher_send(self.hass, f"{DOMAIN}_new_orion_device", new_addr, device_info)
        _LOGGER.info(f"Создан новый сенсор Orion с адресом {new_addr}")
    
    async def _update_dpls_device(self, kdl_addr, old_addr, new_addr):
        """Обновление DPLS устройства после смены адреса"""
        
        old_key = f"{kdl_addr}_{old_addr}"
        new_key = f"{kdl_addr}_{new_addr}"
        
        dpls_devices = self.hass.data.get(DOMAIN, {}).get("dpls_devices", {})
        dpls_entities = self.hass.data.get(DOMAIN, {}).get("dpls_entities", [])
        device_info = dpls_devices.pop(old_key, None)
        
        if not device_info:
            _LOGGER.error(f"DPLS устройство {old_key} не найдено")
            return
        
        # Обновляем адрес
        device_info["dpls_address"] = new_addr
        dpls_devices[new_key] = device_info
        
        # Получаем entity registry
        ent_reg = er.async_get(self.hass)
        old_entity_id = f"sensor.{DOMAIN}_dpls_{old_key}"
        old_entity = ent_reg.async_get(old_entity_id)
        
        if old_entity:
            # Удаляем старый сенсор
            ent_reg.async_remove(old_entity.entity_id)
            _LOGGER.info(f"Удалён старый DPLS сенсор {old_key}")
            
            # Удаляем из списка dpls_entities
            for entity_obj in dpls_entities[:]:
                if hasattr(entity_obj, 'device_key') and entity_obj.device_key == old_key:
                    dpls_entities.remove(entity_obj)
                    break
        
        # Создаём новый сенсор
        async_dispatcher_send(self.hass, f"{DOMAIN}_new_dpls_device", new_key, device_info)
        _LOGGER.info(f"Создан новый DPLS сенсор {new_key}")
