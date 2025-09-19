"""Constants for the Chedraui Shopping List integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "chedraui_shopping_list"

CONF_STORE_ID = "store_id"

DEFAULT_STORE_ID = "10151"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)

SERVICE_ADD_ITEM = "add_item"
SERVICE_REMOVE_ITEM = "remove_item"
SERVICE_UPDATE_ITEM = "update_item"
SERVICE_SET_QUANTITY = "set_quantity"
SERVICE_SEARCH_PRODUCTS = "search_products"

ATTR_QUANTITY = "quantity"
ATTR_UNIT = "unit"
ATTR_WEIGHT = "weight"
ATTR_MEASUREMENT_TYPE = "measurement_type"

PIECE_UNIT = "EA"
WEIGHT_UNIT_KG = "KGM"
WEIGHT_UNIT_G = "GRM"
WEIGHT_UNIT_LB = "LBR"
VOLUME_UNIT_L = "LTR"
VOLUME_UNIT_ML = "MLT"

MEASUREMENT_TYPE_PIECE = "piece"
MEASUREMENT_TYPE_WEIGHT = "weight"
MEASUREMENT_TYPE_VOLUME = "volume"

SUPPORTED_MEASUREMENT_TYPES = {
    MEASUREMENT_TYPE_PIECE,
    MEASUREMENT_TYPE_WEIGHT,
    MEASUREMENT_TYPE_VOLUME,
}

UNIT_ALIASES: dict[str, str] = {
    "pieza": PIECE_UNIT,
    "piezas": PIECE_UNIT,
    "pz": PIECE_UNIT,
    "pieza(s)": PIECE_UNIT,
    "piece": PIECE_UNIT,
    "pieces": PIECE_UNIT,
    "ea": PIECE_UNIT,
    "unit": PIECE_UNIT,
    "units": PIECE_UNIT,
    "unidad": PIECE_UNIT,
    "unidades": PIECE_UNIT,
    "kg": WEIGHT_UNIT_KG,
    "kilogram": WEIGHT_UNIT_KG,
    "kilograms": WEIGHT_UNIT_KG,
    "kilogramo": WEIGHT_UNIT_KG,
    "kilogramos": WEIGHT_UNIT_KG,
    "kilo": WEIGHT_UNIT_KG,
    "kilos": WEIGHT_UNIT_KG,
    "g": WEIGHT_UNIT_G,
    "gr": WEIGHT_UNIT_G,
    "gram": WEIGHT_UNIT_G,
    "grams": WEIGHT_UNIT_G,
    "gramo": WEIGHT_UNIT_G,
    "gramos": WEIGHT_UNIT_G,
    "lb": WEIGHT_UNIT_LB,
    "lbs": WEIGHT_UNIT_LB,
    "pound": WEIGHT_UNIT_LB,
    "pounds": WEIGHT_UNIT_LB,
    "l": VOLUME_UNIT_L,
    "lt": VOLUME_UNIT_L,
    "liter": VOLUME_UNIT_L,
    "liters": VOLUME_UNIT_L,
    "litro": VOLUME_UNIT_L,
    "litros": VOLUME_UNIT_L,
    "ml": VOLUME_UNIT_ML,
    "mililitro": VOLUME_UNIT_ML,
    "mililitros": VOLUME_UNIT_ML,
}

UNIT_TO_MEASUREMENT_TYPE: dict[str, str] = {
    PIECE_UNIT: MEASUREMENT_TYPE_PIECE,
    WEIGHT_UNIT_KG: MEASUREMENT_TYPE_WEIGHT,
    WEIGHT_UNIT_G: MEASUREMENT_TYPE_WEIGHT,
    WEIGHT_UNIT_LB: MEASUREMENT_TYPE_WEIGHT,
    VOLUME_UNIT_L: MEASUREMENT_TYPE_VOLUME,
    VOLUME_UNIT_ML: MEASUREMENT_TYPE_VOLUME,
}
