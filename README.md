# Chedraui Shopping List Home Assistant Integration

This repository provides a custom [Home Assistant](https://www.home-assistant.io/) integration that keeps a shopping list entity in sync with the online cart from [Chedraui México](https://www.chedraui.com.mx/).

## Features

- Config Flow based setup that authenticates with your Chedraui account.
- Represents the current Chedraui cart as a Home Assistant to-do (shopping list) entity.
- Supports adding, removing, and updating items directly from Home Assistant.
- Synchronizes quantities including piece, weight, and volume based units.
- Exposes helper services for programmatic workflows and product search.

## Installation

1. Copy the `custom_components/chedraui_shopping_list` directory into your Home Assistant `custom_components` folder.
2. Restart Home Assistant.
3. Add the integration from **Settings → Devices & Services → Add Integration → Chedraui Shopping List**.
4. Provide your Chedraui credentials and (optionally) the store ID (defaults to `10151`).

## Usage

- A new to-do entity (shopping list) will appear. Items represent the content of your Chedraui cart.
- Create items from the UI by entering either a product ID or name (the integration will search for matches). You can include quantity information in the description (e.g. `2 kg` or `3 piezas`).
- Marking an item as completed removes it from the Chedraui cart.
- Adjusting item details (quantity, unit) updates the remote cart accordingly.

### Services

The integration registers additional services under the `chedraui_shopping_list` domain:

- `add_item`: Add a product to the cart using a known product ID.
- `remove_item`: Remove a line item from the cart.
- `update_item` / `set_quantity`: Modify quantity, unit, or weight for existing items.
- `search_products`: Query the Chedraui catalog (supports service responses).

Refer to `custom_components/chedraui_shopping_list/services.yaml` for the detailed field descriptions.

## Disclaimer

This integration relies on the public endpoints used by the Chedraui website. As the site evolves, the endpoints or authentication flow may change, requiring updates to the integration. Use responsibly and in accordance with the Chedraui terms of service.
