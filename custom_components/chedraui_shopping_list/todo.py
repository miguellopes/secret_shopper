"""Todo platform implementation for the Chedraui Shopping List."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Iterable

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CartItem, ChedrauiClient
from .const import (
    ATTR_MEASUREMENT_TYPE,
    ATTR_QUANTITY,
    ATTR_UNIT,
    DOMAIN,
    UNIT_ALIASES,
    UNIT_TO_MEASUREMENT_TYPE,
)
from .coordinator import ChedrauiDataUpdateCoordinator
from . import IntegrationData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: IntegrationData = hass.data[DOMAIN][entry.entry_id]
    client: ChedrauiClient = data.client
    coordinator: ChedrauiDataUpdateCoordinator = data.coordinator

    async_add_entities([ChedrauiShoppingListEntity(entry, client, coordinator)])


class ChedrauiShoppingListEntity(
    CoordinatorEntity[ChedrauiDataUpdateCoordinator], TodoListEntity
):
    """Representation of the Chedraui shopping cart as a todo list."""

    _attr_has_entity_name = True
    _attr_name = "Shopping List"

    def __init__(
        self,
        entry: ConfigEntry,
        client: ChedrauiClient,
        coordinator: ChedrauiDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_shopping_list"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Chedraui",
            name="Chedraui Shopping Cart",
        )

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.last_update_success)

    async def async_get_items(self) -> list[TodoItem]:
        items: Iterable[CartItem] = self.coordinator.data or []
        return [self._cart_item_to_todo(item) for item in items]

    async def async_create_todo_item(self, item: TodoItem) -> TodoItem:
        product_id: str | None = None
        quantity: float = 1.0
        unit: str | None = None
        measurement_type: str | None = None

        if item.extra:
            product_id = _normalize_str(item.extra.get("product_id"))
            unit = self._normalize_unit(item.extra.get(ATTR_UNIT))
            measurement_type = _normalize_str(item.extra.get(ATTR_MEASUREMENT_TYPE))
            extra_quantity = _coerce_float(item.extra.get(ATTR_QUANTITY), default=None)
            if extra_quantity is not None:
                quantity = extra_quantity

        if item.description:
            parsed = _parse_text(item.description)
            quantity = parsed.quantity or quantity
            unit = parsed.unit or unit
            measurement_type = parsed.measurement_type or measurement_type
            if parsed.product_id:
                product_id = parsed.product_id

        if product_id is None:
            product_id = await self._resolve_product_id(item.summary)
            if product_id is None:
                raise ValueError("Unable to find product for item")

        created = await self._client.async_add_to_cart(
            product_id=product_id,
            quantity=quantity,
            unit=unit,
            measurement_type=measurement_type,
        )
        await self.coordinator.async_request_refresh()
        return self._cart_item_to_todo(created)

    async def async_update_todo_item(self, item: TodoItem) -> TodoItem:
        if item.uid is None:
            raise ValueError("Todo item UID is required")

        if item.status == TodoItemStatus.COMPLETED:
            await self._client.async_remove_from_cart(item.uid)
            await self.coordinator.async_request_refresh()
            return item

        quantity: float | None = None
        unit: str | None = None
        measurement_type: str | None = None

        if item.extra:
            quantity = _coerce_float(item.extra.get(ATTR_QUANTITY), default=None)
            unit = self._normalize_unit(item.extra.get(ATTR_UNIT))
            measurement_type = _normalize_str(item.extra.get(ATTR_MEASUREMENT_TYPE))

        if item.description:
            parsed = _parse_text(item.description)
            quantity = parsed.quantity or quantity
            unit = parsed.unit or unit
            measurement_type = parsed.measurement_type or measurement_type

        await self._client.async_update_cart_item(
            item_id=item.uid,
            quantity=quantity,
            unit=unit,
            measurement_type=measurement_type,
        )
        await self.coordinator.async_request_refresh()
        refreshed = next(
            (i for i in self.coordinator.data or [] if i.item_id == item.uid),
            None,
        )
        return self._cart_item_to_todo(refreshed) if refreshed else item

    async def async_delete_todo_item(self, uid: str) -> None:
        await self._client.async_remove_from_cart(uid)
        await self.coordinator.async_request_refresh()

    async def _resolve_product_id(self, summary: str) -> str | None:
        summary = summary.strip()
        if not summary:
            return None
        if summary.isdigit():
            return summary
        results = await self._client.async_search_products(query=summary, limit=1)
        if not results:
            _LOGGER.warning("No products found for '%s'", summary)
            return None
        return results[0].product_id

    def _cart_item_to_todo(self, item: CartItem | None) -> TodoItem:
        if item is None:
            return TodoItem(summary="", status=TodoItemStatus.NEEDS_ACTION)
        description = (
            f"Cantidad: {item.quantity} {item.unit}"
            if item.unit
            else f"Cantidad: {item.quantity}"
        )
        extra = {
            "product_id": item.product_id,
            ATTR_QUANTITY: item.quantity,
            ATTR_UNIT: item.unit,
            ATTR_MEASUREMENT_TYPE: item.measurement_type,
        }
        return TodoItem(
            summary=item.name,
            uid=item.item_id,
            status=TodoItemStatus.NEEDS_ACTION,
            description=description,
            extra=extra,
        )

    def _normalize_unit(self, unit: Any | None) -> str | None:
        if unit is None:
            return None
        if isinstance(unit, str) and unit:
            return UNIT_ALIASES.get(unit.lower(), unit.upper())
        return None


@dataclass
class ParsedText:
    quantity: float | None
    unit: str | None
    measurement_type: str | None
    product_id: str | None


def _parse_text(text: str) -> ParsedText:
    quantity: float | None = None
    unit: str | None = None
    measurement_type: str | None = None
    product_id: str | None = None

    match = _DESCRIPTION_REGEX.search(text)
    if match:
        quantity = _coerce_float(match.group("quantity"), default=None)
        unit_text = match.group("unit")
        if unit_text:
            unit = UNIT_ALIASES.get(unit_text.lower(), unit_text.upper())
            measurement_type = UNIT_TO_MEASUREMENT_TYPE.get(unit)

    product_match = _PRODUCT_ID_REGEX.search(text)
    if product_match:
        product_id = product_match.group("product_id")

    return ParsedText(quantity, unit, measurement_type, product_id)


def _coerce_float(value: Any, *, default: float | None) -> float | None:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return default
    return default


def _normalize_str(value: Any | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value.strip()
    return None


_DESCRIPTION_REGEX = re.compile(
    r"(?P<quantity>\d+(?:[\.,]\d+)?)\s*(?P<unit>[a-zA-Záéíóúñ]+)",
    re.IGNORECASE,
)

_PRODUCT_ID_REGEX = re.compile(r"product_id\s*[:=]\s*(?P<product_id>\w+)", re.IGNORECASE)
