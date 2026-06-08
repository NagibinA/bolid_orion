"""MQTT клиент для Bolid Orion"""

import asyncio
import logging
import paho.mqtt.client as mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, TOPIC_ANSWER

_LOGGER = logging.getLogger(__name__)

class OrionMQTTClient:
    """MQTT клиент для общения с шлюзом"""

    def __init__(self, hass: HomeAssistant, config: dict):
        self.hass = hass
        self.config = config
        self.client = None
        self._connected = False
        
    async def connect(self):
        """Подключение к MQTT брокеру"""
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        if self.config.get("username"):
            self.client.username_pw_set(
                self.config["username"],
                self.config.get("password")
            )
        
        def do_connect():
            self.client.connect(
                self.config["broker"],
                self.config["port"],
                keepalive=60
            )
            self.client.loop_start()
        
        await self.hass.async_add_executor_job(do_connect)
        
        # Ждём подключения
        for _ in range(10):
            if self._connected:
                break
            await asyncio.sleep(0.5)
        
        if self._connected:
            # Подписываемся на топик ответов
            self.client.subscribe(TOPIC_ANSWER)
            _LOGGER.info(f"Подключен к MQTT брокеру {self.config['broker']}, подписан на {TOPIC_ANSWER}")
        else:
            _LOGGER.error("Не удалось подключиться к MQTT брокеру")
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback при подключении"""
        if rc == 0:
            self._connected = True
            _LOGGER.info(f"MQTT подключен, код={rc}")
        else:
            self._connected = False
            _LOGGER.error(f"Ошибка подключения MQTT, код={rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback при отключении"""
        self._connected = False
        _LOGGER.warning(f"MQTT отключен, код={rc}")
    
    def _on_message(self, client, userdata, msg):
        """Callback при получении сообщения"""
        payload = msg.payload.decode()
        _LOGGER.debug(f"Получено сообщение: {msg.topic} -> {payload}")
        
        # Отправляем сигнал в Home Assistant
        async_dispatcher_send(self.hass, f"{DOMAIN}_message", payload)
    
    async def disconnect(self):
        """Отключение от MQTT брокера"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False
    
    async def send_command(self, command: str):
        """Отправка команды в шлюз"""
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен, команда не отправлена")
            return False
        
        def do_publish():
            self.client.publish(TOPIC_COMMAND, command)
        
        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug(f"Команда отправлена: {command}")
        return True
