"""Config Flow для Bolid Orion"""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

DATA_SCHEMA = vol.Schema({
    vol.Required("broker"): str,
    vol.Required("port", default=1883): int,
    vol.Optional("username"): str,
    vol.Optional("password"): str,
})

class BolidOrionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow для Bolid Orion"""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Шаг настройки"""
        errors = {}

        if user_input is not None:
            # Проверяем подключение к MQTT
            valid = await self._test_connection(
                user_input["broker"],
                user_input["port"],
                user_input.get("username"),
                user_input.get("password"),
            )
            
            if valid:
                return self.async_create_entry(
                    title=f"Bolid Orion ({user_input['broker']})",
                    data=user_input,
                )
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, broker, port, username, password):
        """Тест подключения к MQTT брокеру"""
        import paho.mqtt.client as mqtt
        import socket
        
        result = False
        
        def on_connect(client, userdata, flags, rc):
            nonlocal result
            if rc == 0:
                result = True
            client.disconnect()
        
        client = mqtt.Client()
        client.on_connect = on_connect
        
        if username:
            client.username_pw_set(username, password)
        
        try:
            client.connect(broker, port, 5)
            client.loop_start()
            await asyncio.sleep(2)
            client.loop_stop()
        except:
            result = False
        
        return result

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Опции интеграции"""
        return BolidOrionOptionsFlow(config_entry)


class BolidOrionOptionsFlow(config_entries.OptionsFlow):
    """Опции интеграции (пока пустые, но можно расширить)"""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Шаг опций"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        return self.async_show_form(step_id="init")
