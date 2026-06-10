"""Координатор для управления данными и устройствами."""

import asyncio
import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, ORION_DEVICE_TYPES, DPLS_DEVICE_TYPES, STATUS_CODES
from .const import RSP_ORION, RSP_DPLS, RSP_STATUS
from .mqtt_client import OrionMQTTClient

_LOGGER = logging.getLogger(__name__)


class BolidOrionCoordinator(DataUpdateCoordinator):
    """Координатор для управления данными и устройствами."""

    def __init__(self, hass: HomeAssistant, mqtt_client: OrionMQTTClient, entry_id: str):
        """Инициализация координатора."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),  # Опрос каждые 30 секунд
        )
        self.mqtt_client = mqtt_client
        self.entry_id = entry_id
        self.orion_devices = {}      # {address: device_info}
        self.dpls_devices = {}       # {device_key: device_info}
        self.kdl_addresses = []
        self._scan_complete = False

    async def _async_setup(self):
        """Однократная инициализация при запуске (сканирование Orion и DPLS)."""
        _LOGGER.info("Запуск начального сканирования Orion устройств (адреса 1-127)")
        
        # 1. Сканируем Orion адреса 1-127
        for addr in range(1, 128):
            command = f"{addr};6;0;13;0;0"
            response = await self.mqtt_client.send_command_and_wait(command, timeout=0.3)
            await self._process_orion_response(response, addr)
            await asyncio.sleep(0.1)
        
        _LOGGER.info(f"Сканирование Orion завершено. Найдено устройств: {len(self.orion_devices)}")
        
        # 2. Сканируем DPLS для каждого найденного КДЛ
        for kdl_addr in self.kdl_addresses:
            await self._scan_dpls_line(kdl_addr)
        
        self._scan_complete = True
        _LOGGER.info(f"Начальное сканирование полностью завершено. Orion: {len(self.orion_devices)}, DPLS: {len(self.dpls_devices)}")
        
        # Уведомляем об изменении устройств
        self.async_update_listeners()

    async def _async_update_data(self):
        """Периодическое обновление данных (статус DPLS)."""
        if not self._scan_complete:
            return {"status": "initial_scan_not_complete"}
        
        if not self.dpls_devices:
            return {"status": "no_dpls_devices"}
        
        _LOGGER.debug(f"Периодический опрос статуса {len(self.dpls_devices)} DPLS устройств")
        
        # Обновляем статус для каждого DPLS устройства
        for device_key, device_info in self.dpls_devices.items():
            kdl_address = device_info.get("kdl_address")
            dpls_address = device_info.get("dpls_address")
            
            if kdl_address and dpls_address:
                await self._poll_dpls_status(kdl_address, dpls_address, device_key)
                await asyncio.sleep(0.3)  # Пауза между запросами
        
        return {"status": "updated"}

    async def _scan_dpls_line(self, kdl_address: int):
        """Однократное синхронное сканирование DPLS линии (адреса 1-127)."""
        _LOGGER.info(f"Сканирование DPLS для КДЛ адрес {kdl_address}")
        
        for dpls_addr in range(1, 128):
            command = f"{kdl_address};6;0;57;{dpls_addr};1"
            response = await self.mqtt_client.send_command_and_wait(command, timeout=0.3)
            await self._process_dpls_response(response, kdl_address, dpls_addr)
            await asyncio.sleep(0.1)

    async def _poll_dpls_status(self, kdl_addr: int, dpls_addr: int, device_key: str):
        """Опрос статуса DPLS устройства (команда 25)."""
        command = f"{kdl_addr};6;0;25;{dpls_addr};0"
        response = await self.mqtt_client.send_command_and_wait(command, timeout=0.3)
        await self._process_status_response(response, device_key)

    async def _process_orion_response(self, response: str, expected_addr: int):
        """Обработка ответа на команду 13 (Orion)."""
        if not response:
            return
        
        parts = response.strip().split()
        if len(parts) < 8:
            return
        
        try:
            rsp_type = int(parts[2])
            if rsp_type != RSP_ORION:
                return
            
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
            
            _LOGGER.info(f"Найден Orion прибор: адрес {address} -> {device_name}")
            
            if address not in self.orion_devices:
                self.orion_devices[address] = {
                    "name": device_name,
                    "type_code": device_type,
                    "firmware": version,
                }
                # Отправляем сигнал о новом устройстве
                async_dispatcher_send(self.hass, f"{DOMAIN}_new_orion_device", address)
                
                if device_type == 9 and address not in self.kdl_addresses:
                    self.kdl_addresses.append(address)
                    _LOGGER.info(f"Добавлен КДЛ адрес {address}")
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга Orion ответа: {e}")

    async def _process_dpls_response(self, response: str, kdl_addr: int, requested_addr: int):
        """Обработка ответа на команду 57 (DPLS поиск)."""
        if not response:
            return
        
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
                
                _LOGGER.info(f"Найден DPLS прибор: КДЛ {kdl_addr}, DPLS адрес {requested_addr}, тип {device_name}")
                
                device_key = f"{kdl_addr}_{requested_addr}"
                
                if device_key not in self.dpls_devices:
                    self.dpls_devices[device_key] = {
                        "name": device_name,
                        "type_code": dpls_type,
                        "kdl_address": kdl_addr,
                        "dpls_address": requested_addr,
                        "status_code": None,
                        "status_text": None,
                    }
                    # Отправляем сигнал о новом устройстве
                    async_dispatcher_send(self.hass, f"{DOMAIN}_new_dpls_device", device_key)
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга DPLS ответа: {e}")

    async def _process_status_response(self, response: str, device_key: str):
        """Обработка ответа на команду 25 (статус)."""
        if not response:
            return
        
        parts = response.strip().split()
        if len(parts) < 5:
            return
        
        try:
            rsp_type = int(parts[2])
            if rsp_type != RSP_STATUS:
                return
            
            status_code = int(parts[4])
            status_text = STATUS_CODES.get(status_code, f"Неизвестно")
            
            if device_key in self.dpls_devices:
                self.dpls_devices[device_key]["status_code"] = status_code
                self.dpls_devices[device_key]["status_text"] = status_text
                # Уведомляем об обновлении статуса
                async_dispatcher_send(self.hass, f"{DOMAIN}_update_dpls_status", device_key, status_code, status_text)
                _LOGGER.debug(f"Обновлён статус DPLS {device_key}: {status_text} (код {status_code})")
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга статуса: {e}")

    def get_orion_devices(self):
        """Получить все Orion устройства."""
        return self.orion_devices

    def get_dpls_devices(self):
        """Получить все DPLS устройства."""
        return self.dpls_devices
