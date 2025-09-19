"""Asynchronous client for interacting with Chedraui."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any, Iterable

import async_timeout
from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    MEASUREMENT_TYPE_PIECE,
    MEASUREMENT_TYPE_VOLUME,
    MEASUREMENT_TYPE_WEIGHT,
    UNIT_ALIASES,
    UNIT_TO_MEASUREMENT_TYPE,
)

_LOGGER = logging.getLogger(__name__)

LOGIN_PATH_TEMPLATE = "/wcs/resources/store/{store_id}/loginidentity"
CART_PATH_TEMPLATE = "/wcs/resources/store/{store_id}/cart"
CART_ITEM_PATH_TEMPLATE = "/wcs/resources/store/{store_id}/cart/@self/{item_id}"
CART_SELF_PATH_TEMPLATE = "/wcs/resources/store/{store_id}/cart/@self"
SEARCH_PATH_TEMPLATE = "/wcs/resources/store/{store_id}/productview/bySearchTerm/{query}"

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "HomeAssistant/chedraui_shopping_list (+https://www.home-assistant.io/)",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

REQUEST_TIMEOUT = 30


class ChedrauiError(Exception):
    """Base exception for Chedraui errors."""


class ChedrauiAuthError(ChedrauiError):
    """Authentication error."""


class ChedrauiRequestError(ChedrauiError):
    """Raised when Chedraui returns an error response."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(slots=True)
class CartItem:
    """Representation of an item in the Chedraui cart."""

    item_id: str
    product_id: str
    name: str
    quantity: float
    unit: str
    measurement_type: str
    price: float | None = None
    original_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class ProductSummary:
    """Summary for a Chedraui product."""

    product_id: str
    sku: str | None
    name: str
    price: float | None
    unit: str | None
    measurement_type: str | None
    category: str | None = None
    brand: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sku": self.sku,
            "name": self.name,
            "price": self.price,
            "unit": self.unit,
            "measurement_type": self.measurement_type,
            "category": self.category,
            "brand": self.brand,
        }


class ChedrauiClient:
    """API client for interacting with the Chedraui store."""

    base_url: str = "https://www.chedraui.com.mx"

    def __init__(
        self,
        *,
        session: ClientSession,
        username: str,
        password: str,
        store_id: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._store_id = store_id
        self._cookies: dict[str, str] = {}
        self._is_authenticated = False
        self.available_units = sorted({*UNIT_TO_MEASUREMENT_TYPE.keys()})
        self.measurement_types = sorted(
            {MEASUREMENT_TYPE_PIECE, MEASUREMENT_TYPE_WEIGHT, MEASUREMENT_TYPE_VOLUME}
        )

    async def async_login(self) -> None:
        """Authenticate against the Chedraui platform."""
        payload = {
            "logonId": self._username,
            "logonPassword": self._password,
        }

        response = await self._request(
            "POST",
            LOGIN_PATH_TEMPLATE.format(store_id=self._store_id),
            json=payload,
            allow_reauth=False,
        )

        if response is None:
            raise ChedrauiAuthError("Unexpected empty authentication response")

        self._is_authenticated = True

    async def async_ensure_authenticated(self) -> None:
        if not self._is_authenticated:
            await self.async_login()

    async def async_get_cart(self) -> list[CartItem]:
        """Retrieve the current cart contents."""
        await self.async_ensure_authenticated()
        data = await self._request(
            "GET",
            CART_SELF_PATH_TEMPLATE.format(store_id=self._store_id),
        )
        return self._parse_cart_items(data)

    async def async_add_to_cart(
        self,
        *,
        product_id: str,
        quantity: float = 1.0,
        unit: str | None = None,
        weight: float | None = None,
        measurement_type: str | None = None,
    ) -> CartItem:
        await self.async_ensure_authenticated()

        normalized_unit = self._normalize_unit(unit, measurement_type)
        payload: dict[str, Any] = {
            "orderItem": [
                {
                    "productId": str(product_id),
                    "quantity": quantity,
                }
            ]
        }

        if normalized_unit:
            payload["orderItem"][0]["uom"] = normalized_unit
        if weight is not None:
            payload["orderItem"][0]["weight"] = weight

        data = await self._request(
            "POST",
            CART_PATH_TEMPLATE.format(store_id=self._store_id),
            json=payload,
        )

        items = self._parse_cart_items(data)
        if not items:
            raise ChedrauiRequestError("Failed to add item to cart")
        return items[-1]

    async def async_update_cart_item(
        self,
        *,
        item_id: str,
        quantity: float | None = None,
        unit: str | None = None,
        weight: float | None = None,
        measurement_type: str | None = None,
    ) -> list[CartItem]:
        await self.async_ensure_authenticated()

        if quantity is None and unit is None and weight is None and measurement_type is None:
            _LOGGER.debug("No update data provided for item %s", item_id)
            return await self.async_get_cart()

        normalized_unit = self._normalize_unit(unit, measurement_type)
        payload: dict[str, Any] = {"orderItem": [{}]}
        payload_item = payload["orderItem"][0]
        payload_item["orderItemId"] = str(item_id)

        if quantity is not None:
            payload_item["quantity"] = quantity
        if normalized_unit is not None:
            payload_item["uom"] = normalized_unit
        if weight is not None:
            payload_item["weight"] = weight

        data = await self._request(
            "PUT",
            CART_PATH_TEMPLATE.format(store_id=self._store_id),
            json=payload,
        )
        return self._parse_cart_items(data)

    async def async_remove_from_cart(self, item_id: str) -> None:
        await self.async_ensure_authenticated()
        await self._request(
            "DELETE",
            CART_ITEM_PATH_TEMPLATE.format(store_id=self._store_id, item_id=item_id),
        )

    async def async_search_products(
        self, *, query: str, limit: int = 10
    ) -> list[ProductSummary]:
        await self.async_ensure_authenticated()
        params = {
            "pageSize": str(limit),
            "responseFormat": "json",
            "pageNumber": "1",
            "searchType": "keyword",
        }
        path = SEARCH_PATH_TEMPLATE.format(store_id=self._store_id, query=query)
        data = await self._request("GET", path, params=params)
        return self._parse_search_results(data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any | None = None,
        allow_reauth: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = dict(DEFAULT_HEADERS)

        async with async_timeout.timeout(REQUEST_TIMEOUT):
            try:
                response: ClientResponse
                response = await self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                    cookies=self._cookies,
                )
            except ClientError as err:
                raise ChedrauiRequestError(
                    f"Error communicating with Chedraui: {err}"
                ) from err

        await self._update_cookies(response)

        if response.status == 401 and allow_reauth:
            self._is_authenticated = False
            await self.async_login()
            return await self._request(
                method,
                path,
                params=params,
                json=json,
                allow_reauth=False,
            )

        if response.status >= 400:
            content = await response.text()
            _LOGGER.debug(
                "Chedraui request failed: %s %s (status: %s, body: %s)",
                method,
                url,
                response.status,
                content,
            )
            if response.status == 401:
                raise ChedrauiAuthError("Authentication to Chedraui failed")
            raise ChedrauiRequestError(
                f"Chedraui error ({response.status}) while requesting {path}",
                status=response.status,
            )

        if response.content_type == "application/json":
            return await response.json()

        text = await response.text()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.debug("Received non-JSON response for %s %s: %s", method, path, text)
            return text

    async def _update_cookies(self, response: ClientResponse) -> None:
        for name, morsel in response.cookies.items():
            value = morsel.value
            if value is None:
                continue
            self._cookies[name] = value

    def _parse_cart_items(self, data: Any) -> list[CartItem]:
        if not data:
            return []

        order_items: Iterable[dict[str, Any]] = []
        if isinstance(data, dict):
            order_items = data.get("orderItem") or data.get("orderItems") or []
        elif isinstance(data, list):
            order_items = data

        items: list[CartItem] = []
        for raw in order_items:
            if raw is None:
                continue
            item_id = str(raw.get("orderItemId") or raw.get("id") or raw.get("itemId") or "")
            product_id = str(
                raw.get("productId")
                or raw.get("catEntryId")
                or raw.get("catalogEntryId")
                or raw.get("productPartNumber")
                or ""
            )
            if not item_id:
                continue
            name = self._extract_name(raw)
            quantity = self._extract_float(raw.get("quantity"), default=1.0)
            unit = self._extract_unit(raw)
            measurement_type = UNIT_TO_MEASUREMENT_TYPE.get(unit, MEASUREMENT_TYPE_PIECE)
            price = self._extract_float(
                raw.get("price")
                or raw.get("offerPrice")
                or raw.get("unitPrice")
                or raw.get("orderItemAmount"),
                default=None,
            )
            items.append(
                CartItem(
                    item_id=item_id,
                    product_id=product_id,
                    name=name,
                    quantity=quantity,
                    unit=unit,
                    measurement_type=measurement_type,
                    price=price,
                    original_payload=raw,
                )
            )
        return items

    def _extract_name(self, raw: dict[str, Any]) -> str:
        for key in ("productName", "name", "description"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                return value
        return "Producto"

    def _extract_unit(self, raw: dict[str, Any]) -> str:
        for key in ("uom", "unitOfMeasure", "unit", "measure"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                normalized = UNIT_ALIASES.get(value.lower())
                return normalized or value.upper()
        measurement = raw.get("measurementUnit") or raw.get("measurement")
        if isinstance(measurement, str) and measurement:
            normalized = UNIT_ALIASES.get(measurement.lower())
            if normalized:
                return normalized
        return "EA"

    def _normalize_unit(
        self, unit: str | None, measurement_type: str | None
    ) -> str | None:
        if unit is None and measurement_type is None:
            return None

        normalized_unit: str | None = None
        if unit:
            normalized_unit = UNIT_ALIASES.get(unit.lower(), unit.upper())
        elif measurement_type:
            normalized_unit = self._default_unit_for_measurement(measurement_type)

        if normalized_unit is None:
            return None

        if normalized_unit not in UNIT_TO_MEASUREMENT_TYPE:
            _LOGGER.debug("Unknown unit %s, falling back to piece", normalized_unit)
            return UNIT_ALIASES.get("ea", "EA")
        return normalized_unit

    def _default_unit_for_measurement(self, measurement_type: str) -> str | None:
        measurement_type = measurement_type.lower()
        if measurement_type == MEASUREMENT_TYPE_PIECE:
            return "EA"
        if measurement_type == MEASUREMENT_TYPE_WEIGHT:
            return "KGM"
        if measurement_type == MEASUREMENT_TYPE_VOLUME:
            return "LTR"
        return None

    def _extract_float(self, value: Any, *, default: float | None) -> float | None:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(",", ".")
            try:
                return float(cleaned)
            except ValueError:
                return default
        return default

    def _parse_search_results(self, data: Any) -> list[ProductSummary]:
        if not data:
            return []

        raw_items: Iterable[dict[str, Any]]
        if isinstance(data, dict):
            if "catalogEntryView" in data:
                raw_items = data["catalogEntryView"]
            elif "product" in data and isinstance(data["product"], dict):
                raw_items = data["product"].get("docs", [])
            else:
                raw_items = data.get("items", [])
        elif isinstance(data, list):
            raw_items = data
        else:
            return []

        results: list[ProductSummary] = []
        for raw in raw_items:
            if raw is None:
                continue
            product_id = str(
                raw.get("partNumber")
                or raw.get("uniqueID")
                or raw.get("productId")
                or raw.get("id")
                or ""
            )
            if not product_id:
                continue
            sku = str(raw.get("sku") or raw.get("partNumber") or product_id)
            name = self._extract_search_name(raw)
            price = self._extract_float(
                raw.get("price")
                or raw.get("offerPrice")
                or raw.get("bestPrice")
                or raw.get("unitPrice"),
                default=None,
            )
            unit = self._extract_search_unit(raw)
            measurement_type = (
                UNIT_TO_MEASUREMENT_TYPE.get(unit)
                if unit
                else self._infer_measurement_type_from_name(name)
            )
            brand = raw.get("brand")
            category = None
            categories = raw.get("category") or raw.get("categoryPath")
            if isinstance(categories, list) and categories:
                category = categories[-1] if isinstance(categories[-1], str) else None
            results.append(
                ProductSummary(
                    product_id=product_id,
                    sku=sku,
                    name=name,
                    price=price,
                    unit=unit,
                    measurement_type=measurement_type,
                    category=category,
                    brand=brand,
                )
            )
        return results

    def _extract_search_name(self, raw: dict[str, Any]) -> str:
        for key in ("name", "productName", "shortDescription", "description"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                return value
        return "Producto"

    def _extract_search_unit(self, raw: dict[str, Any]) -> str | None:
        for key in ("uom", "unitOfMeasure", "unit", "measure"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                normalized = UNIT_ALIASES.get(value.lower())
                return normalized or value.upper()
        unit_desc = raw.get("unitOfMeasureText") or raw.get("measurement")
        if isinstance(unit_desc, str):
            normalized = UNIT_ALIASES.get(unit_desc.lower())
            if normalized:
                return normalized
        quantity_desc = raw.get("measurement") or raw.get("measure")
        if isinstance(quantity_desc, str):
            match = _UNIT_IN_TEXT_REGEX.search(quantity_desc)
            if match:
                unit = match.group("unit")
                return UNIT_ALIASES.get(unit.lower(), unit.upper())
        return None

    def _infer_measurement_type_from_name(self, name: str) -> str | None:
        match = _UNIT_IN_TEXT_REGEX.search(name)
        if not match:
            return None
        unit = UNIT_ALIASES.get(match.group("unit").lower())
        if not unit:
            return None
        return UNIT_TO_MEASUREMENT_TYPE.get(unit)


_UNIT_IN_TEXT_REGEX = re.compile(
    r"(?P<value>\d+(?:[\.,]\d+)?)\s*(?P<unit>[a-zA-Záéíóúñ]+)",
    re.IGNORECASE,
)
