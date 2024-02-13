from typing import Any

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult


class DeviceToolsConfigFlow(ConfigFlow, domain="dummy"):
    """Device Tools config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""

        await self.async_set_unique_id("dummy")
        self._abort_if_unique_id_configured(updates=user_input)

        return self.async_create_entry(title="Dummy", data={})
