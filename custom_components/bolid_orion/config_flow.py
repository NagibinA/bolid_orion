"""Config Flow для Bolid Orion"""

import voluptuous as vol
from homeassistant import config_entries
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

    async def async_step_user(self, user_input=None):
        """Шаг настройки"""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Bolid Orion ({user_input['broker']})",
                data=user_input
            )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
