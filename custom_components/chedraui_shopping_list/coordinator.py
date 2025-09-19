"""Data update coordinator for the Chedraui Shopping List integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import CartItem, ChedrauiClient, ChedrauiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ChedrauiDataUpdateCoordinator(DataUpdateCoordinator[list[CartItem]]):
    """Coordinator that retrieves the current cart items."""

    def __init__(self, hass: HomeAssistant, client: ChedrauiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} cart",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self) -> list[CartItem]:
        return await self._client.async_get_cart()
