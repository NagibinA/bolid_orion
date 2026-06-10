"""MQTT клиент для Bolid Orion с синхронными запросами"""

import asyncio
import logging
import uuid
import paho.mqtt.client as mqtt
from homeassistant.helpers.dispatcher import dispatcher_send
from .const import DOMAIN, TOPIC_COMMAND, TOPIC_ANSWER

_LOGGER = logging.getLogger(__name__)

class OrionMQTTClient:
    def __init__(self, hass, config: dict):
        self.hass = hass
        self.config = config
        self.client = None
        self._connected = False
        self._pending = {}

    async def connect(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
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

        for _ in range(10):
            if self._connected:
                break
            await asyncio.sleep(0.5)

        if self._connected:
            self.client.subscribe(TOPIC_ANSWER)
            _LOGGER.info(f"Подключен к MQTT брокеру {self.config['broker']}")
        else:
            _LOGGER.error("Не удалось подключиться к MQTT брокеру")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            _LOGGER.info(f"MQTT подключен")
        else:
            self._connected = False
            _LOGGER.error(f"Ошибка подключения MQTT, код={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        _LOGGER.warning(f"MQTT отключен")

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        _LOGGER.debug(f"Получено: {msg.topic} -> {payload}")
        
        # Проверяем, есть ли ожидающий Future
        if self._pending:
            # Берём первый ожидающий Future (FIFO)
            first_cmd_id = next(iter(self._pending))
            ctx = self._pending[first_cmd_id]
            if ctx.get("type") == "wait":
                ctx["future"].set_result(payload)
                del self._pending[first_cmd_id]
                return
        
        # Для всех остальных сообщений
        dispatcher_send(self.hass, f"{DOMAIN}_message", {"payload": payload})

    async def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False

    async def send_command(self, command: str):
        """Отправка команды без ожидания ответа"""
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен")
            return False

        def do_publish():
            self.client.publish(TOPIC_COMMAND, command)

        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug(f"Команда отправлена: {command}")
        return True

    async def send_command_and_wait(self, command: str, timeout: float = 0.5):
        """Отправить команду и дождаться ответа"""
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен")
            return None
        
        future = asyncio.Future()
        cmd_id = str(uuid.uuid4())
        self._pending[cmd_id] = {"future": future, "type": "wait"}
        
        def do_publish():
            self.client.publish(TOPIC_COMMAND, command)
        
        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug(f"Команда отправлена с ожиданием: {command}")
        
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            _LOGGER.debug(f"Таймаут ожидания ответа: {command}")
            return None
        finally:
            self._pending.pop(cmd_id, None)
