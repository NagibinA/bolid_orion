"""MQTT клиент для Bolid Orion Protocol v2.0.0"""

import asyncio
import logging
import uuid
import paho.mqtt.client as mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, TOPIC_COMMAND, TOPIC_ANSWER

_LOGGER = logging.getLogger(__name__)


class OrionMQTTClient:
    """Клиент для работы с MQTT брокером"""
    
    def __init__(self, hass: HomeAssistant, broker: str, port: int = 1883,
                 username: str = None, password: str = None):
        """Инициализация MQTT клиента"""
        self.hass = hass
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self._connected = False
        self._pending_requests = {}  # {request_id: {"future": future, "expected_type": int, "timestamp": float}}
    
    async def connect(self) -> bool:
        """Подключение к MQTT брокеру"""
        # Создаем клиент с версией API 2.0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # Настройка аутентификации
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        
        # Подключаемся в отдельном потоке
        def do_connect():
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
        
        await self.hass.async_add_executor_job(do_connect)
        
        # Ждем подключения (максимум 5 секунд)
        for _ in range(10):
            if self._connected:
                break
            await asyncio.sleep(0.5)
        
        # Подписываемся на топик ответов
        if self._connected:
            self.client.subscribe(TOPIC_ANSWER)
            _LOGGER.info("MQTT подключен к %s:%s", self.broker, self.port)
        else:
            _LOGGER.error("Не удалось подключиться к MQTT брокеру %s:%s", self.broker, self.port)
        
        return self._connected
    
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Обработчик подключения"""
        if reason_code == 0:
            self._connected = True
            _LOGGER.info("MQTT подключен успешно")
        else:
            self._connected = False
            _LOGGER.error("Ошибка подключения MQTT, код: %s", reason_code)
    
    def _on_disconnect(self, client, userdata, reason_code, properties):
        """Обработчик отключения"""
        self._connected = False
        _LOGGER.warning("MQTT отключен, код: %s", reason_code)
    
    def _on_message(self, client, userdata, msg):
        """Обработчик входящих сообщений"""
        payload = msg.payload.decode()
        _LOGGER.debug("Получено сообщение [%s]: %s", msg.topic, payload)
        
        # Парсим ответ
        parts = payload.strip().split()
        if len(parts) >= 3:
            try:
                rsp_type = int(parts[2])
                
                # Ищем ожидающий запрос с таким типом ответа
                for req_id, req_data in list(self._pending_requests.items()):
                    if req_data["expected_type"] == rsp_type:
                        if not req_data["future"].done():
                            req_data["future"].set_result(payload)
                        del self._pending_requests[req_id]
                        return
            except (ValueError, IndexError):
                pass
        
        # Если нет ожидающего запроса, отправляем в диспетчер
        async_dispatcher_send(self.hass, f"{DOMAIN}_message", payload)
    
    async def send_command(self, command: str) -> bool:
        """Отправка команды без ожидания ответа"""
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен, команда не отправлена")
            return False
        
        def do_publish():
            self.client.publish(TOPIC_COMMAND, command)
        
        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug("Команда отправлена: %s", command)
        return True
    
    async def send_command_and_wait(self, command: str, expected_type: int, timeout: float = 5.0):
        """Отправка команды и ожидание ответа с определенным типом"""
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен")
            return None
        
        # Очищаем просроченные запросы
        self._cleanup_pending()
        
        # Создаем новый запрос
        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        self._pending_requests[request_id] = {
            "future": future,
            "expected_type": expected_type,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Отправляем команду
        def do_publish():
            self.client.publish(TOPIC_COMMAND, command)
        
        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug("Команда отправлена с ожиданием типа %s: %s", expected_type, command)
        
        # Ждем ответ
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            _LOGGER.debug("Таймаут %s сек для команды: %s", timeout, command)
            return None
        finally:
            self._pending_requests.pop(request_id, None)
    
    def _cleanup_pending(self):
        """Очистка просроченных запросов (старше 10 секунд)"""
        now = asyncio.get_event_loop().time()
        timeout = 10
        
        for req_id, req_data in list(self._pending_requests.items()):
            if now - req_data["timestamp"] > timeout:
                if not req_data["future"].done():
                    req_data["future"].set_result(None)
                del self._pending_requests[req_id]
                _LOGGER.debug("Очищен просроченный запрос %s", req_id)
    
    async def disconnect(self):
        """Отключение от MQTT брокера"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False
            _LOGGER.info("MQTT клиент отключен")
        
        # Отменяем все ожидающие запросы
        for req_data in self._pending_requests.values():
            if not req_data["future"].done():
                req_data["future"].set_result(None)
        self._pending_requests.clear()
