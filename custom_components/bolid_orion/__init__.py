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
    hass.data[DOMAIN]["dpls_entities"] = []  # ← сохраняем ссылки на сенсоры
    hass.data[DOMAIN]["kdl_addresses"] = []
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["scan_in_progress"] = False
    hass.data[DOMAIN]["polling_started"] = False
    
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
    """Сканирование Orion адресов 1-127 (синхронно)"""
    
    if hass.data[DOMAIN].get("scan_in_progress"):
        return
    
    hass.data[DOMAIN]["scan_in_progress"] = True
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, "Сканирование Orion: подготовка...")
    _LOGGER.info("Начало сканирования Orion (адреса 1-127)")
    
    for addr in range(1, 128):
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование Orion: адрес {addr} из 127")
        command = f"{addr};6;0;13;0;0"
        response = await mqtt_client.send_command_and_wait(command, expected_rsp_type=RSP_ORION, timeout=2.0)
        
        if response:
            await process_orion_response(hass, response, addr)
        
        await asyncio.sleep(0.1)
    
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование Orion завершено. Найдено: {len(hass.data[DOMAIN]['orion_devices'])}")
    _LOGGER.info(f"Сканирование Orion завершено. Найдено: {len(hass.data[DOMAIN]['orion_devices'])}")
    
    for kdl_addr in hass.data[DOMAIN]["kdl_addresses"]:
        await scan_dpls_line(hass, mqtt_client, kdl_addr)
    
    orion_count = len(hass.data[DOMAIN]["orion_devices"])
    dpls_count = len(hass.data[DOMAIN]["dpls_devices"])
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование завершено. Orion: {orion_count}, DPLS: {dpls_count}")
    _LOGGER.info(f"Сканирование завершено. Orion: {orion_count}, DPLS: {dpls_count}")
    
    hass.data[DOMAIN]["scan_in_progress"] = False
    
    # Запускаем циклический опрос статуса ТОЛЬКО после завершения сканирования
    if not hass.data[DOMAIN].get("polling_started"):
        hass.data[DOMAIN]["polling_started"] = True
        await start_status_polling(hass, mqtt_client)


async def scan_dpls_line(hass, mqtt_client, kdl_address):
    """Синхронное сканирование DPLS линии (адреса 1-127)"""
    
    _LOGGER.info(f"Сканирование DPLS для КДЛ {kdl_address}")
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование DPLS: КДЛ {kdl_address}")
    
    for dpls_addr in range(1, 128):
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование DPLS: КДЛ {kdl_address}, адрес {dpls_addr} из 127")
        command = f"{kdl_address};6;0;57;{dpls_addr};1"
        
        response = await mqtt_client.send_command_and_wait(command, expected_rsp_type=RSP_DPLS, timeout=2.0)
        
        if response:
            await process_dpls_response(hass, response, kdl_address, dpls_addr)
        
        await asyncio.sleep(0.1)


async def process_orion_response(hass, response, expected_addr):
    """Обработка ответа на команду 13"""
    parts = response.strip().split()
    if len(parts) < 8:
        return
    
    try:
        address = int(parts[0])
        if address != expected_addr:
            return
        
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


async def process_dpls_response(hass, response, kdl_address, requested_addr):
    """Обработка ответа на команду 57"""
    parts = response.strip().split()
    if len(parts) < 5:
        return
    
    try:
        rsp_type = int(parts[2])
        if rsp_type != RSP_DPLS:
            return
        
        device_exists = int(parts[3])
        dpls_type = int(parts[4])
        
        if device_exists != 0 and dpls_type != 0:
            device_name = DPLS_DEVICE_TYPES.get(dpls_type, f"Тип {dpls_type}")
            
            _LOGGER.info(f"Найден DPLS: КДЛ {kdl_address}, DPLS адрес {requested_addr}, тип {device_name}")
            
            dpls_devices = hass.data[DOMAIN]["dpls_devices"]
            device_key = f"{kdl_address}_{requested_addr}"
            
            if device_key not in dpls_devices:
                dpls_devices[device_key] = {
                    "name": device_name,
                    "type_code": dpls_type,
                    "kdl_address": kdl_address,
                    "dpls_address": requested_addr,
                    "status_code": None,
                    "status_text": None,
                }
                async_dispatcher_send(hass, f"{DOMAIN}_new_dpls_device", device_key, dpls_devices[device_key])
    except (ValueError, IndexError) as e:
        _LOGGER.error(f"Ошибка парсинга DPLS: {e}")


async def start_status_polling(hass, mqtt_client):
    """Циклический опрос статуса DPLS устройств (по одному за раз)"""
    
    _LOGGER.info("Запуск циклического опроса статуса DPLS устройств")
    
    while True:
        dpls_devices = hass.data[DOMAIN].get("dpls_devices", {})
        
        if dpls_devices:
            for device_key, device_info in dpls_devices.items():
                kdl_address = device_info.get("kdl_address")
                dpls_address = device_info.get("dpls_address")
                
                if kdl_address and dpls_address:
                    command = f"{kdl_address};6;0;25;{dpls_address};0"
                    response = await mqtt_client.send_command_and_wait(command, expected_rsp_type=RSP_STATUS, timeout=2.0)
                    
                    if response:
                        await process_status_response(hass, response, device_key)
                    
                    await asyncio.sleep(0.5)
        
        await asyncio.sleep(10)


async def process_status_response(hass, response, device_key):
    """Обработка ответа на команду 25 (статус)"""
    parts = response.strip().split()
    if len(parts) < 5:
        return
    
    try:
        status_code = int(parts[4])
        status_text = STATUS_CODES.get(status_code, f"Неизвестно")
        
        _LOGGER.info(f"Статус DPLS {device_key}: код {status_code} -> {status_text}")
        
        dpls_devices = hass.data[DOMAIN]["dpls_devices"]
        if device_key in dpls_devices:
            dpls_devices[device_key]["status_code"] = status_code
            dpls_devices[device_key]["status_text"] = status_text
            
            # Обновляем сенсор напрямую
            for entity in hass.data[DOMAIN].get("dpls_entities", []):
                if hasattr(entity, 'device_key') and entity.device_key == device_key:
                    entity.update_status(status_code, status_text)
                    _LOGGER.info(f"Сенсор {device_key} обновлён: {status_text}")
                    break
    except (ValueError, IndexError) as e:
        _LOGGER.error(f"Ошибка парсинга статуса: {e}")


async def process_message(hass, data):
    """Обработка ответов (для неожиданных сообщений)"""
    
    if DOMAIN not in hass.data:
        return
    
    if isinstance(data, str):
        data = {"payload": data}
    
    payload = data.get("payload")
    
    if not payload:
        return
    
    parts = payload.strip().split()
    if len(parts) < 5:
        return
    
    try:
        rsp_type = int(parts[2])
    except:
        return
    
    if rsp_type == RSP_STATUS and len(parts) >= 5:
        try:
            kdl_address = int(parts[0])
            dpls_addr = int(parts[3])
            status_code = int(parts[4])
            
            device_key = f"{kdl_address}_{dpls_addr}"
            status_text = STATUS_CODES.get(status_code, f"Неизвестно")
            
            dpls_devices = hass.data[DOMAIN].get("dpls_devices", {})
            if device_key in dpls_devices:
                dpls_devices[device_key]["status_code"] = status_code
                dpls_devices[device_key]["status_text"] = status_text
                
                for entity in hass.data[DOMAIN].get("dpls_entities", []):
                    if hasattr(entity, 'device_key') and entity.device_key == device_key:
                        entity.update_status(status_code, status_text)
                        break
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга статуса: {e}")