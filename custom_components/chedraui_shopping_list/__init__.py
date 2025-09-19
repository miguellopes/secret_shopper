"""The Chedraui Shopping List integration."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from aiohttp import ClientError, ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import ChedrauiAuthError, ChedrauiClient, ChedrauiError
from .const import (
    CONF_STORE_ID,
    DEFAULT_STORE_ID,
    DOMAIN,
    SERVICE_ADD_ITEM,
    SERVICE_REMOVE_ITEM,
    SERVICE_SEARCH_PRODUCTS,
    SERVICE_SET_QUANTITY,
    SERVICE_UPDATE_ITEM,
)
from .coordinator import ChedrauiDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TODO]


def _build_client(hass: HomeAssistant, entry: ConfigEntry) -> ChedrauiClient:
    session: ClientSession = async_get_clientsession(hass)
    store_id: str = entry.data.get(CONF_STORE_ID, DEFAULT_STORE_ID)
    return ChedrauiClient(
        session=session,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        store_id=store_id,
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Chedraui Shopping List integration from YAML."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Chedraui Shopping List config entry."""
    client = _build_client(hass, entry)

    try:
        await client.async_login()
    except ChedrauiAuthError as err:
        raise ConfigEntryNotReady("Authentication failed") from err
    except ClientError as err:
        raise ConfigEntryNotReady("Unable to communicate with Chedraui") from err

    coordinator = ChedrauiDataUpdateCoordinator(hass, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ChedrauiError as err:
        raise ConfigEntryNotReady("Unable to fetch initial cart state") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = IntegrationData(
        client=client,
        coordinator=coordinator,
        service_unsubscribers=[],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Chedraui Shopping List config entry."""
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        return True

    integration_data: IntegrationData = hass.data[DOMAIN][entry.entry_id]

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        for unsub in integration_data.service_unsubscribers:
            unsub()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


@dataclass
class IntegrationData:
    """Data for an active config entry."""

    client: ChedrauiClient
    coordinator: ChedrauiDataUpdateCoordinator
    service_unsubscribers: list[Callable[[], None]]


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    integration_data: IntegrationData = hass.data[DOMAIN][entry.entry_id]
    client = integration_data.client
    coordinator = integration_data.coordinator

    async def handle_add(call: ServiceCall) -> None:
        await client.async_add_to_cart(
            product_id=str(call.data["product_id"]),
            quantity=call.data.get("quantity", 1.0),
            unit=call.data.get("unit"),
            weight=call.data.get("weight"),
            measurement_type=call.data.get("measurement_type"),
        )
        await coordinator.async_request_refresh()

    async def handle_remove(call: ServiceCall) -> None:
        await client.async_remove_from_cart(str(call.data["item_id"]))
        await coordinator.async_request_refresh()

    async def handle_update(call: ServiceCall) -> None:
        await client.async_update_cart_item(
            item_id=str(call.data["item_id"]),
            quantity=call.data.get("quantity"),
            unit=call.data.get("unit"),
            weight=call.data.get("weight"),
            measurement_type=call.data.get("measurement_type"),
        )
        await coordinator.async_request_refresh()

    async def handle_set_quantity(call: ServiceCall) -> None:
        await client.async_update_cart_item(
            item_id=str(call.data["item_id"]),
            quantity=call.data.get("quantity"),
            unit=call.data.get("unit"),
            weight=call.data.get("weight"),
            measurement_type=call.data.get("measurement_type"),
        )
        await coordinator.async_request_refresh()

    async def handle_search(call: ServiceCall) -> dict[str, Any]:
        query = str(call.data["query"])
        limit = call.data.get("limit", 10)
        results = await client.async_search_products(query=query, limit=limit)
        return {"results": [result.to_dict() for result in results]}

    add_schema = vol.Schema(
        {
            vol.Required("product_id"): vol.Any(int, str),
            vol.Optional("quantity", default=1.0): vol.Coerce(float),
            vol.Optional("unit"): vol.Any(None, vol.Coerce(str)),
            vol.Optional("measurement_type"): vol.Any(None, vol.Coerce(str)),
            vol.Optional("weight"): vol.Coerce(float),
        }
    )
    remove_schema = vol.Schema({vol.Required("item_id"): vol.Any(int, str)})
    update_schema = vol.Schema(
        {
            vol.Required("item_id"): vol.Any(int, str),
            vol.Optional("quantity"): vol.Coerce(float),
            vol.Optional("unit"): vol.Any(None, vol.Coerce(str)),
            vol.Optional("measurement_type"): vol.Any(None, vol.Coerce(str)),
            vol.Optional("weight"): vol.Coerce(float),
        }
    )
    search_schema = vol.Schema(
        {
            vol.Required("query"): vol.Coerce(str),
            vol.Optional("limit", default=10): vol.All(int, vol.Range(min=1, max=50)),
        }
    )

    integration_data.service_unsubscribers.append(
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_ITEM,
            handle_add,
            schema=add_schema,
        )
    )
    integration_data.service_unsubscribers.append(
        hass.services.async_register(
            DOMAIN,
            SERVICE_REMOVE_ITEM,
            handle_remove,
            schema=remove_schema,
        )
    )
    integration_data.service_unsubscribers.append(
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_ITEM,
            handle_update,
            schema=update_schema,
        )
    )
    integration_data.service_unsubscribers.append(
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_QUANTITY,
            handle_set_quantity,
            schema=update_schema,
        )
    )
    integration_data.service_unsubscribers.append(
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEARCH_PRODUCTS,
            handle_search,
            schema=search_schema,
            supports_response=True,
        )
    )
