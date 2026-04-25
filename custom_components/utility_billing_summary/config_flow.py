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
    BILLING_MODES,
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
    COST_BILLING_MODE,
    COST_NAME,
    DEFAULT_AUTO_SEND,
    DEFAULT_BILLING_MODE,
    DEFAULT_CURRENCY,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_TLS,
    DOMAIN,
    OPT_AUTO_SEND,
    OPT_CURRENCY,
    OPT_FIXED_COSTS,
    OPT_RECIPIENTS,
    OPT_UTILITIES,
    SOURCE_ENERGY,
    SOURCE_MANUAL,
    UTIL_CATEGORY,
    UTIL_ENTITY_ID,
    UTIL_NAME,
    UTIL_RATE,
    UTIL_SOURCE,
    UTIL_STAT_COST,
    UTIL_STAT_ENERGY_FROM,
    UTIL_UNIT,
)
from .energy import async_available_sources


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
            vol.Required(
                CONF_SMTP_PASSWORD, default=d.get(CONF_SMTP_PASSWORD, "")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(
                CONF_SMTP_TLS, default=d.get(CONF_SMTP_TLS, DEFAULT_SMTP_TLS)
            ): bool,
            vol.Required(
                CONF_SMTP_SENDER, default=d.get(CONF_SMTP_SENDER, "")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
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
        self._energy_sources: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        utilities = self._working.get(OPT_UTILITIES, [])
        fixed = self._working.get(OPT_FIXED_COSTS, [])
        recipients = self._working.get(OPT_RECIPIENTS, [])
        summary = (
            f"Encje: {len(utilities)} · Koszty stałe: {len(fixed)} · "
            f"Odbiorcy: {len(recipients)}"
        )
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "utilities_menu",
                "fixed_costs_menu",
                "recipients",
                "smtp",
                "preferences",
                "send_test",
                "save",
            ],
            description_placeholders={"summary": summary},
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _utility_label(row: dict[str, Any]) -> str:
        src = row.get(UTIL_SOURCE, SOURCE_MANUAL)
        mark = "🔌" if src == SOURCE_ENERGY else "✏️"
        name = row.get(UTIL_NAME, "?")
        cat = row.get(UTIL_CATEGORY, "")
        unit = row.get(UTIL_UNIT, "")
        if src == SOURCE_ENERGY:
            return f"{mark} {name} — {cat} (Energy Dashboard)"
        rate = row.get(UTIL_RATE, 0)
        return f"{mark} {name} — {cat} ({rate}/{unit})"

    @staticmethod
    def _fixed_label(row: dict[str, Any]) -> str:
        name = row.get(COST_NAME, "?")
        amount = row.get(COST_AMOUNT, 0)
        mode = row.get(COST_BILLING_MODE, DEFAULT_BILLING_MODE)
        mode_label = "z góry" if mode == "prepaid" else "z dołu"
        return f"{name} — {amount} ({mode_label})"

    def _utilities_summary(self) -> str:
        rows = self._working.get(OPT_UTILITIES, [])
        if not rows:
            return "Brak dodanych encji."
        return "\n".join(
            f"{i}. {self._utility_label(r)}" for i, r in enumerate(rows, 1)
        )

    def _fixed_summary(self) -> str:
        rows = self._working.get(OPT_FIXED_COSTS, [])
        if not rows:
            return "Brak dodanych kosztów stałych."
        return "\n".join(f"{i}. {self._fixed_label(r)}" for i, r in enumerate(rows, 1))

    # ------------------------------------------------------------------ utilities
    async def async_step_utilities_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="utilities_menu",
            menu_options=[
                "utility_add_energy",
                "utility_add",
                "utility_remove",
                "init",
            ],
            description_placeholders={"summary": self._utilities_summary()},
        )

    async def async_step_utility_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            utilities = list(self._working.get(OPT_UTILITIES, []))
            utilities.append(
                {
                    UTIL_SOURCE: SOURCE_MANUAL,
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

    async def async_step_utility_add_energy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a utility row sourced from HA Energy Dashboard."""
        if not self._energy_sources:
            self._energy_sources = await async_available_sources(self.hass)

        if not self._energy_sources:
            return self.async_abort(reason="no_energy_sources")

        if user_input is not None:
            idx = int(user_input["source_index"])
            if 0 <= idx < len(self._energy_sources):
                src = self._energy_sources[idx]
                utilities = list(self._working.get(OPT_UTILITIES, []))
                utilities.append(
                    {
                        UTIL_SOURCE: SOURCE_ENERGY,
                        UTIL_NAME: user_input.get(UTIL_NAME) or src["name"],
                        UTIL_CATEGORY: user_input.get(UTIL_CATEGORY, src["category"]),
                        UTIL_UNIT: user_input.get(UTIL_UNIT, src["unit"]),
                        UTIL_STAT_ENERGY_FROM: src["stat_energy_from"],
                        UTIL_STAT_COST: src["stat_cost"],
                    }
                )
                self._working[OPT_UTILITIES] = utilities
            return await self.async_step_init()

        options = [
            {
                "value": str(i),
                "label": f"{src['name']} ({src['category']})",
            }
            for i, src in enumerate(self._energy_sources)
        ]
        first = self._energy_sources[0]
        schema = vol.Schema(
            {
                vol.Required("source_index", default="0"): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(UTIL_NAME, default=first["name"]): str,
                vol.Required(UTIL_CATEGORY, default=first["category"]): SelectSelector(
                    SelectSelectorConfig(
                        options=CATEGORIES,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="utility_category",
                    )
                ),
                vol.Required(UTIL_UNIT, default=first["unit"]): str,
            }
        )
        return self.async_show_form(step_id="utility_add_energy", data_schema=schema)

    async def async_step_utility_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        utilities: list[dict[str, Any]] = list(self._working.get(OPT_UTILITIES, []))
        if not utilities:
            return await self.async_step_utilities_menu()

        if user_input is not None:
            indices = sorted(
                {int(v) for v in user_input.get("indices", [])},
                reverse=True,
            )
            for idx in indices:
                if 0 <= idx < len(utilities):
                    utilities.pop(idx)
            self._working[OPT_UTILITIES] = utilities
            return await self.async_step_utilities_menu()

        options = [
            {"value": str(i), "label": self._utility_label(u)}
            for i, u in enumerate(utilities)
        ]
        schema = vol.Schema(
            {
                vol.Required("indices", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.LIST,
                        multiple=True,
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
            description_placeholders={"summary": self._fixed_summary()},
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
                    COST_BILLING_MODE: user_input[COST_BILLING_MODE],
                }
            )
            self._working[OPT_FIXED_COSTS] = costs
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(COST_NAME): str,
                vol.Required(COST_AMOUNT, default=0.0): NumberSelector(
                    NumberSelectorConfig(min=0, step=0.01, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    COST_BILLING_MODE, default=DEFAULT_BILLING_MODE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=BILLING_MODES,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="billing_mode",
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
            return await self.async_step_fixed_costs_menu()

        if user_input is not None:
            indices = sorted(
                {int(v) for v in user_input.get("indices", [])},
                reverse=True,
            )
            for idx in indices:
                if 0 <= idx < len(costs):
                    costs.pop(idx)
            self._working[OPT_FIXED_COSTS] = costs
            return await self.async_step_fixed_costs_menu()

        options = [
            {"value": str(i), "label": self._fixed_label(c)}
            for i, c in enumerate(costs)
        ]
        schema = vol.Schema(
            {
                vol.Required("indices", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.LIST,
                        multiple=True,
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
        schema = vol.Schema({vol.Required("recipients", default=current): str})
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

    async def async_step_send_test(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Trigger the `send_test_email` service from the options flow."""
        recipients = self._working.get(OPT_RECIPIENTS, [])
        if not recipients:
            return self.async_abort(reason="no_recipients")

        if user_input is not None:
            try:
                await self.hass.services.async_call(
                    DOMAIN,
                    "send_test_email",
                    {"recipients": recipients},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001
                return self.async_abort(reason="send_failed")
            return self.async_abort(reason="test_sent")

        return self.async_show_form(
            step_id="send_test",
            data_schema=vol.Schema({}),
            description_placeholders={"recipients": ", ".join(recipients)},
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self._working)
