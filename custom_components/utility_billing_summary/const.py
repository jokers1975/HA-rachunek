"""Constants for the Utility Bill Summary integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "utility_billing_summary"
PLATFORMS: list[Platform] = [Platform.SENSOR]

# Config entry keys (immutable — stored in entry.data)
CONF_TITLE = "title"
CONF_SMTP_HOST = "smtp_host"
CONF_SMTP_PORT = "smtp_port"
CONF_SMTP_USER = "smtp_user"
CONF_SMTP_PASSWORD = "smtp_password"
CONF_SMTP_TLS = "smtp_tls"
CONF_SMTP_SENDER = "smtp_sender"

# Option keys (mutable — stored in entry.options)
OPT_UTILITIES = "utilities"
OPT_FIXED_COSTS = "fixed_costs"
OPT_RECIPIENTS = "recipients"
OPT_CURRENCY = "currency"
OPT_AUTO_SEND = "auto_send"

# Per-utility row keys
UTIL_ENTITY_ID = "entity_id"
UTIL_NAME = "name"
UTIL_RATE = "rate"
UTIL_UNIT = "unit"
UTIL_CATEGORY = "category"

# Per-fixed-cost row keys
COST_NAME = "name"
COST_AMOUNT = "amount"
COST_BILLING_MODE = "billing_mode"

# Billing modes for fixed costs
BILLING_PREPAID = "prepaid"   # paid in advance — period labelled with the NEXT month
BILLING_POSTPAID = "postpaid"  # paid in arrears — labelled with the report month
BILLING_MODES = [BILLING_POSTPAID, BILLING_PREPAID]

# Defaults
DEFAULT_CURRENCY = "PLN"
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_TLS = True
DEFAULT_AUTO_SEND = True
DEFAULT_BILLING_MODE = BILLING_POSTPAID
HISTORY_MONTHS = 12
UPDATE_INTERVAL_HOURS = 1

# Scheduler — report generated on the 1st day at 09:00 local
REPORT_DAY = 1
REPORT_HOUR = 9
REPORT_MINUTE = 0

# Storage
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "utility_billing_summary"

# Categories (used for grouping and icons on the invoice card)
CATEGORY_ELECTRICITY = "electricity"
CATEGORY_GAS = "gas"
CATEGORY_WATER = "water"
CATEGORY_HEATING = "heating"
CATEGORY_OTHER = "other"
CATEGORIES = [
    CATEGORY_ELECTRICITY,
    CATEGORY_GAS,
    CATEGORY_WATER,
    CATEGORY_HEATING,
    CATEGORY_OTHER,
]

# Service names
SERVICE_SEND_MONTHLY_REPORT = "send_monthly_report"
SERVICE_GENERATE_PREVIEW = "generate_preview"
SERVICE_SEND_TEST_EMAIL = "send_test_email"

# Frontend — card is bundled inside the integration so HACS ships it along the code
CARD_URL_PATH = f"/{DOMAIN}/utility-bill-card.js"
CARD_FILENAME = "utility-bill-card.js"
CARD_SUBDIR = "frontend"
