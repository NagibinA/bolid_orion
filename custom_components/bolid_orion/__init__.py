"""Интеграция Bolid Orion Protocol"""

import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .const import DOMAIN, ORION_DEVICE_TYPES, DPLS_DEVICE_TYPES, STATUS_CODES
from .const import RSP_ORION, RSP_DPLS, RSP_STATUS, SIGNAL_STATUS_UPDATE
from .mqtt_client import OrionMQTTClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции"""
    
    mqtt_client = OrionMQTTClient(hass, entry.data)
    await mqtt_client.connect()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["mqtt_client"] = mqtt_client
    hass.data[DOMAIN]["orion_devices"] = {}
    hass.data[DOMAIN]["dpls_devices"] = {}
    hass.data[DOMAIN]["kdl_addresses"] = []
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["scan_in_progress"] = False
    
    def handle_message(data):
        if isinstance(data, str):
            data = {"payload": data}
        hass.create_task(process_message(hass, data))
    
    async_dispatcher_connect(hass, f"{DOMAIN}_message", handle_message)
    
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])
    
    async def delayed_scan():
        await asyncio.sleep(10)
        await scan_orion_devices(hass, mqtt_client)
    
    entry.async_create_background_task(hass, delayed_scan(), "bolid_orion_scan")
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции"""
    
    mqtt_client = hass.data[DOMAIN].get("mqtt_client")
    if mqtt_client:
        await mqtt_client.disconnect()
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])
    
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    
    return unload_ok


async def scan_orion_devices(hass, mqtt_client):
    """Сканирование Orion адресов 1-127"""
    
    if hass.data[DOMAIN].get("scan_in_progress"):
        return
    
    hass.data[DOMAIN]["scan_in_progress"] = True
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, "Сканирование Orion: подготовка...")
    _LOGGER.info("Начало сканирования Orion (адреса 1-127)")
    
    for addr in range(1, 128):
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование Orion: адрес {addr} из 127")
        command = f"{addr};6;0;13;0;0"
        await mqtt_client.send_command(command)
        await asyncio.sleep(0.3)
    
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование Orion завершено. Найдено: {len(hass.data[DOMAIN]['orion_devices'])}")
    _LOGGER.info(f"Сканирование Orion завершено. Найдено: {len(hass.data[DOMAIN]['orion_devices'])}")
    
    for kdl_addr in hass.data[DOMAIN]["kdl_addresses"]:
        await scan_dpls_line(hass, mqtt_client, kdl_addr)
    
    orion_count = len(hass.data[DOMAIN]["orion_devices"])
    dpls_count = len(hass.data[DOMAIN]["dpls_devices"])
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование завершено. Orion: {orion_count}, DPLS: {dpls_count}")
    _LOGGER.info(f"Сканирование завершено. Orion: {orion_count}, DPLS: {dpls_count}")
    
    hass.data[DOMAIN]["scan_in_progress"] = False


async def scan_dpls_line(hass, mqtt_client, kdl_address):
    """Сканирование DPLS линии для КДЛ (адреса 1-127)"""
    
    _LOGGER.info(f"Сканирование DPLS для КДЛ {kdl_address}")
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование DPLS: КДЛ {kdl_address}")
    
    for dpls_addr in range(1, 128):
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование DPLS: КДЛ {kdl_address}, адрес {dpls_addr} из 127")
        command = f"{kdl_address};6;0;57;{dpls_addr};1"
        context = {
            "type": "dpls_scan",
            "kdl_addr": kdl_address,
            "dpls_addr": dpls_addr
        }
        await mqtt_client.send_command(command, context=context)
        await asyncio.sleep(0.2)


async def poll_dpls_status(hass, mqtt_client, kdl_address, dpls_address, device_key):
    """Однократный опрос статуса DPLS устройства (команда 25)"""
    command = f"{kdl_address};6;0;25;{dpls_address};0"
    context = {
        "type": "dpls_status",
        "kdl_addr": kdl_address,
        "dpls_addr": dpls_address,
        "device_key": device_key,
    }
    await mqtt_client.send_command(command, context=context)


async def process_message(hass, data):
    """Обработка ответов"""
    
    if DOMAIN not in hass.data:
        return
    
    if isinstance(data, str):
        data = {"payload": data}
    
    payload = data.get("payload")
    dpls_addr_from_context = data.get("dpls_addr")
    
    if not payload:
        return
    
    parts = payload.strip().split()
    if len(parts) < 5:
        return
    
    try:
        rsp_type = int(parts[2])
    except:
        return
    
    # ========== ORION ==========
    if rsp_type == RSP_ORION and len(parts) >= 8:
        try:
            address = int(parts[0])
            device_type = int(parts[3])
            
            byte4 = int(parts[4])
            byte5 = int(parts[5])
            devVer = byte4 | (byte5 << 8)
            major = devVer // 100
            minor = devVer % 100
            version = f"{major}.{minor:02d}"
            
            device_name = ORION_DEVICE_TYPES.get(device_type, f"Тип {device_type}")
            
            _LOGGER.info(f"Найден Orion: адрес {address} -> {device_name}")
            
            orion_devices = hass.data[DOMAIN]["orion_devices"]
            
            if address not in orion_devices:
                orion_devices[address] = {
                    "name": device_name,
                    "type_code": device_type,
                    "firmware": version,
                }
                async_dispatcher_send(hass, f"{DOMAIN}_new_orion_device", address, orion_devices[address])
                
                if device_type == 9 and address not in hass.data[DOMAIN]["kdl_addresses"]:
                    hass.data[DOMAIN]["kdl_addresses"].append(address)
                    _LOGGER.info(f"Добавлен КДЛ адрес {address}")
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга Orion: {e}")
    
    # ========== DPLS ==========
    elif rsp_type == RSP_DPLS and len(parts) >= 5:
        try:
            kdl_address = int(parts[0])
            device_exists = int(parts[3])
            dpls_type = int(parts[4])
            
            dpls_addr = dpls_addr_from_context
            
            if device_exists != 0 and dpls_type != 0 and dpls_addr is not None:
                device_name = DPLS_DEVICE_TYPES.get(dpls_type, f"Тип {dpls_type}")
                
                _LOGGER.info(f"Найден DPLS: КДЛ {kdl_address}, DPLS адрес {dpls_addr}, тип {device_name}")
                
                dpls_devices = hass.data[DOMAIN]["dpls_devices"]
                device_key = f"{kdl_address}_{dpls_addr}"
                
                if device_key not in dpls_devices:
                    dpls_devices[device_key] = {
                        "name": device_name,
                        "type_code": dpls_type,
                        "kdl_address": kdl_address,
                        "dpls_address": dpls_addr,
                        "статус": None,
                    }
                    async_dispatcher_send(hass, f"{DOMAIN}_new_dpls_device", device_key, dpls_devices[device_key])
                    
                    # После создания сенсора, сразу опрашиваем статус
                    mqtt_client = hass.data[DOMAIN]["mqtt_client"]
                    await poll_dpls_status(hass, mqtt_client, kdl_address, dpls_addr, device_key)
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга DPLS: {e}")
    
    # ========== СТАТУС DPLS (команда 25) ==========
    elif rsp_type == RSP_STATUS and len(parts) >= 5:
        try:
            kdl_address = int(parts[0])
            dpls_addr = int(parts[3])
            status_code = int(parts[4])
            
            device_key = f"{kdl_address}_{dpls_addr}"
            status_text = STATUS_CODES.get(status_code, f"Код {status_code}")
            
            _LOGGER.debug(f"Статус DPLS: КДЛ {kdl_address}, DPLS {dpls_addr} -> {status_text}")
            
            dpls_devices = hass.data[DOMAIN].get("dpls_devices", {})
            if device_key in dpls_devices:
                dpls_devices[device_key]["статус"] = status_text
                async_dispatcher_send(hass, f"{DOMAIN}_update_dpls_status", device_key, status_text)
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга статуса: {e}")
