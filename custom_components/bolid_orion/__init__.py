"""Интеграция Bolid Orion Protocol"""

import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .mqtt_client import OrionMQTTClient
from .coordinator import BolidOrionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции из Config Entry."""
    
    mqtt_client = OrionMQTTClient(hass, entry.data)
    await mqtt_client.connect()
    
    # Создаем координатор
    coordinator = BolidOrionCoordinator(hass, mqtt_client, entry.entry_id)
    
    # Сохраняем в hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Загружаем платформы
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])
    
    # Запускаем координатор
    await coordinator.async_config_entry_first_refresh()
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции."""
    
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.mqtt_client.disconnect()
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok
