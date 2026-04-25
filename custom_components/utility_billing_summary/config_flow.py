"""Config and options flow for Utility Bill Summary."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CATEGORIES,
    CATEGORY_OTHER,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SENDER,
    CONF_SMTP_TLS,
    CONF_SMTP_USER,
    CONF_TITLE,
    COST_AMOUNT,
    COST_NAME,
    DEFAULT_AUTO_SEND,
    DEFAULT_CURRENCY,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_TLS,
    DOMAIN,
    OPT_AUTO_SEND,
    OPT_CURRENCY,
    OPT_FIXED_COSTS,
    OPT_RECIPIENTS,
    OPT_UTILITIES,
    UTIL_CATEGORY,
    UTIL_ENTITY_ID,
    UTIL_NAME,
    UTIL_RATE,
    UTIL_UNIT,
)


def _smtp_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_TITLE, default=d.get(CONF_TITLE, "Rachunki")): str,
            vol.Required(CONF_SMTP_HOST, default=d.get(CONF_SMTP_HOST, "")): str,
            vol.Required(
                CONF_SMTP_PORT, default=d.get(CONF_SMTP_PORT, DEFAULT_SMTP_PORT)
            ): int,
            vol.Required(CONF_SMTP_USER, default=d.get(CONF_SMTP_USER, "")): str,
            vol.Required(CONF_SMTP_PASSWORD, default=d.get(CONF_SMTP_PASSWORD, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_SMTP_TLS, default=d.get(CONF_SMTP_TLS, DEFAULT_SMTP_TLS)
            ): bool,
            vol.Required(CONF_SMTP_SENDER, default=d.get(CONF_SMTP_SENDER, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL)
            ),
        }
    )


class UtilityBillSummaryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup — instance title + SMTP only."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            title = user_input.pop(CONF_TITLE)
            return self.async_create_entry(
                title=title,
                data=user_input,
                options={
                    OPT_UTILITIES: [],
                    OPT_FIXED_COSTS: [],
                    OPT_RECIPIENTS: [],
                    OPT_CURRENCY: DEFAULT_CURRENCY,
                    OPT_AUTO_SEND: DEFAULT_AUTO_SEND,
                },
            )
        return self.async_show_form(
            step_id="user", data_schema=_smtp_schema(), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return UtilityBillOptionsFlow(entry)


class UtilityBillOptionsFlow(OptionsFlow):
    """Options flow — manage utilities, fixed costs, recipients, SMTP, preferences."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._working: dict[str, Any] = dict(entry.options)
        self._edit_index: int | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "utilities_menu",
                "fixed_costs_menu",
                "recipients",
                "smtp",
                "preferences",
                "save",
            ],
        )

    # ------------------------------------------------------------------ utilities
    async def async_step_utilities_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="utilities_menu",
            menu_options=["utility_add", "utility_remove", "init"],
        )

    async def async_step_utility_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            utilities = list(self._working.get(OPT_UTILITIES, []))
            utilities.append(
                {
                    UTIL_ENTITY_ID: user_input[UTIL_ENTITY_ID],
                    UTIL_NAME: user_input[UTIL_NAME],
                    UTIL_RATE: float(user_input[UTIL_RATE]),
                    UTIL_UNIT: user_input[UTIL_UNIT],
                    UTIL_CATEGORY: user_input[UTIL_CATEGORY],
                }
            )
            self._working[OPT_UTILITIES] = utilities
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(UTIL_ENTITY_ID): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(UTIL_NAME): str,
                vol.Required(UTIL_RATE, default=0.0): NumberSelector(
                    NumberSelectorConfig(
                        min=0, step=0.0001, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(UTIL_UNIT, default="kWh"): str,
                vol.Required(UTIL_CATEGORY, default=CATEGORY_OTHER): SelectSelector(
                    SelectSelectorConfig(
                        options=CATEGORIES,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="utility_category",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="utility_add", data_schema=schema)

    async def async_step_utility_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        utilities: list[dict[str, Any]] = list(self._working.get(OPT_UTILITIES, []))
        if not utilities:
            return await self.async_step_init()

        labels = {
            str(i): f"{u.get(UTIL_NAME)} ({u.get(UTIL_ENTITY_ID)})"
            for i, u in enumerate(utilities)
        }
        if user_input is not None:
            idx = int(user_input["index"])
            if 0 <= idx < len(utilities):
                utilities.pop(idx)
                self._working[OPT_UTILITIES] = utilities
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required("index"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v} for k, v in labels.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="utility_remove", data_schema=schema)

    # ------------------------------------------------------------- fixed costs
    async def async_step_fixed_costs_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="fixed_costs_menu",
            menu_options=["fixed_add", "fixed_remove", "init"],
        )

    async def async_step_fixed_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            costs = list(self._working.get(OPT_FIXED_COSTS, []))
            costs.append(
                {
                    COST_NAME: user_input[COST_NAME],
                    COST_AMOUNT: float(user_input[COST_AMOUNT]),
                }
            )
            self._working[OPT_FIXED_COSTS] = costs
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(COST_NAME): str,
                vol.Required(COST_AMOUNT, default=0.0): NumberSelector(
                    NumberSelectorConfig(
                        min=0, step=0.01, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="fixed_add", data_schema=schema)

    async def async_step_fixed_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        costs: list[dict[str, Any]] = list(self._working.get(OPT_FIXED_COSTS, []))
        if not costs:
            return await self.async_step_init()

        labels = {
            str(i): f"{c.get(COST_NAME)} ({c.get(COST_AMOUNT)})"
            for i, c in enumerate(costs)
        }
        if user_input is not None:
            idx = int(user_input["index"])
            if 0 <= idx < len(costs):
                costs.pop(idx)
                self._working[OPT_FIXED_COSTS] = costs
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required("index"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v} for k, v in labels.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="fixed_remove", data_schema=schema)

    # ---------------------------------------------------------------- misc
    async def async_step_recipients(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        current = ", ".join(self._working.get(OPT_RECIPIENTS, []))
        if user_input is not None:
            raw = user_input["recipients"]
            self._working[OPT_RECIPIENTS] = [
                part.strip() for part in raw.split(",") if part.strip()
            ]
            return await self.async_step_init()
        schema = vol.Schema(
            {vol.Required("recipients", default=current): str}
        )
        return self.async_show_form(step_id="recipients", data_schema=schema)

    async def async_step_smtp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # SMTP credentials live in entry.data — update in-place.
            new_data = dict(self._entry.data)
            new_data.update(user_input)
            new_data.pop(CONF_TITLE, None)
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return await self.async_step_init()
        defaults = {**self._entry.data, CONF_TITLE: self._entry.title}
        return self.async_show_form(step_id="smtp", data_schema=_smtp_schema(defaults))

    async def async_step_preferences(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._working[OPT_CURRENCY] = user_input[OPT_CURRENCY]
            self._working[OPT_AUTO_SEND] = user_input[OPT_AUTO_SEND]
            return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_CURRENCY,
                    default=self._working.get(OPT_CURRENCY, DEFAULT_CURRENCY),
                ): str,
                vol.Required(
                    OPT_AUTO_SEND,
                    default=self._working.get(OPT_AUTO_SEND, DEFAULT_AUTO_SEND),
                ): bool,
            }
        )
        return self.async_show_form(step_id="preferences", data_schema=schema)

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self._working)
