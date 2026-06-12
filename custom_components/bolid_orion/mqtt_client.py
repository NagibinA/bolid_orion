"""MQTT клиент для Bolid Orion Protocol v2.0.0"""

import logging
import asyncio
import uuid
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)


class OrionMQTTClient:
    """MQTT клиент для работы с устройствами Болид"""
    
    def __init__(self, hass, broker, port=1883, username=None, password=None):
        self.hass = hass
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self._connected = False
        self._loop = None
        self._pending_requests = {}
    
    async def connect(self) -> bool:
        try:
            self._loop = asyncio.get_running_loop()
            
            self.client = mqtt.Client()
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            
            if self.username:
                self.client.username_pw_set(self.username, self.password)
            
            def do_connect():
                self.client.connect(self.broker, self.port, 60)
                self.client.loop_start()
            
            await self.hass.async_add_executor_job(do_connect)
            
            for _ in range(10):
                if self._connected:
                    break
                await asyncio.sleep(0.5)
            
            if self._connected:
                self.client.subscribe("WemosOrion/answer")
                _LOGGER.info("MQTT подключен к %s:%s", self.broker, self.port)
            
            return self._connected
            
        except Exception as e:
            _LOGGER.error("Ошибка подключения: %s", e)
            return False
    
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            _LOGGER.info("MQTT подключен")
        else:
            self._connected = False
            _LOGGER.error("Ошибка MQTT, код: %s", rc)
    
    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        _LOGGER.debug("Получено сообщение: %s", payload)
        
        if self._pending_requests:
            parts = payload.strip().split()
            if len(parts) >= 3:
                try:
                    rsp_type = int(parts[2])
                    for req_id, req_data in list(self._pending_requests.items()):
                        if req_data["expected_type"] == rsp_type:
                            if not req_data["future"].done():
                                req_data["future"].set_result(payload)
                            del self._pending_requests[req_id]
                            return
                except (ValueError, IndexError):
                    pass
    
    async def send_command(self, command: str) -> bool:
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен")
            return False
        
        def do_publish():
            self.client.publish("WemosOrion/byteN", command)
        
        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug("Команда отправлена: %s", command)
        return True
    
    async def send_command_and_wait(self, command: str, expected_type: int, timeout: float = 10.0):
        if not self._connected or not self.client:
            _LOGGER.error("MQTT не подключен")
            return None
        
        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        self._pending_requests[request_id] = {
            "future": future,
            "expected_type": expected_type,
        }
        
        def do_publish():
            self.client.publish("WemosOrion/byteN", command)
        
        await self.hass.async_add_executor_job(do_publish)
        _LOGGER.debug("Команда отправлена с ожиданием: %s", command)
        
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            _LOGGER.warning("Таймаут для команды: %s", command)
            return None
        finally:
            self._pending_requests.pop(request_id, None)
    
    async def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False