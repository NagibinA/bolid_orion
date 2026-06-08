import logging
import re
from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, TOPIC_ANSWER, DEVICE_TYPES
from .sensor import OrionDeviceSensor

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Настройка интеграции"""
    
    # Хранилище найденных устройств
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["devices"] = {}
    
    @callback
    async def message_received(msg):
        """Обработка входящих сообщений от шлюза"""
        payload = msg.payload
        _LOGGER.debug(f"Получен ответ: {payload}")
        
        # Парсим строку "2 7 0 44 245 0 5 26"
        parts = payload.strip().split()
        if len(parts) < 8:
            _LOGGER.warning(f"Неверный формат ответа: {payload}")
            return
        
        try:
            address = int(parts[0])
            length = int(parts[1])
            rnd = int(parts[2])
            device_type_code = int(parts[3])
            fw_lo = int(parts[4])
            fw_hi = int(parts[5])
            sub_ver = int(parts[6])
            crc = int(parts[7])
            
            # Формируем версию прошивки
            firmware = f"{fw_hi}.{fw_lo}.{sub_ver}"
            
            # Получаем информацию о типе прибора
            device_info = DEVICE_TYPES.get(device_type_code, {
                "name": f"Неизвестный прибор (код {device_type_code})",
                "loops": 0,
                "relays": 0
            })
            
            device_info["type_code"] = device_type_code
            device_info["firmware"] = firmware
            device_info["address"] = address
            
            _LOGGER.info(f"Найден прибор: адрес={address}, тип={device_info['name']}, версия={firmware}")
            
            # Проверяем, создан ли уже сенсор для этого адреса
            devices = hass.data[DOMAIN]["devices"]
            if address not in devices:
                # Отправляем сигнал для создания сенсора
                async_dispatcher_send(hass, f"{DOMAIN}_new_device", address, device_info)
                devices[address] = device_info
            else:
                # Обновляем существующий сенсор
                old_device = devices[address]
                if old_device.get("firmware") != firmware:
                    old_device["firmware"] = firmware
                    # Находим и обновляем сенсор
                    for entity in hass.data[DOMAIN].get("entities", []):
                        if entity._address == address:
                            entity.update_device_info(device_info)
                            break
                devices[address] = device_info
                
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Ошибка парсинга ответа {payload}: {e}")
    
    # Подписываемся на топик ответов
    await mqtt.async_subscribe(hass, TOPIC_ANSWER, message_received, 0)
    
    return True
