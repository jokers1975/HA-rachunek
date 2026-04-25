/**
 * Utility Bill custom card — invoice-styled Lovelace card for the
 * `utility_billing_summary` integration. Reads the MonthTotalSensor entity
 * and renders a paper-invoice layout based on its attributes.
 */

const CARD_VERSION = "0.1.0";

const CATEGORY_ICONS = {
  electricity: "⚡",
  gas: "🔥",
  water: "💧",
  heating: "🌡️",
  other: "•",
};

const PL_MONTHS = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
];

function formatMoney(value, currency) {
  const v = Number(value || 0);
  const formatted = v.toFixed(2).replace(".", ",");
  return `${formatted} ${currency || ""}`.trim();
}

function formatPeriod(isoMonth) {
  if (!isoMonth) return "";
  const [y, m] = isoMonth.split("-");
  const idx = parseInt(m, 10) - 1;
  return `${PL_MONTHS[idx] || ""} ${y}`;
}

class UtilityBillCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("hui-generic-entity-row");
  }

  static getStubConfig() {
    return { entity: "sensor.rachunek_miesieczny" };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Wymagane pole: entity");
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const state = this._hass.states[this._config.entity];
    if (!state) {
      this.innerHTML = `<ha-card><div style="padding:16px;">Encja ${this._config.entity} nie istnieje</div></ha-card>`;
      return;
    }
    const attrs = state.attributes || {};
    const currency = attrs.currency || "PLN";
    const period = formatPeriod(attrs.month);
    const breakdown = attrs.breakdown || [];
    const fixed = attrs.fixed_costs || [];
    const total = Number(state.state || 0);
    const title = this._config.title || "Rachunek za media";

    const rows = breakdown.map((line) => {
      const icon = CATEGORY_ICONS[line.category] || CATEGORY_ICONS.other;
      const cons = Number(line.consumption || 0).toFixed(2);
      const rate = Number(line.rate || 0).toFixed(4);
      return `
        <tr>
          <td><span class="cat">${icon}</span>${line.name || ""}</td>
          <td class="num">${cons} ${line.unit || ""}</td>
          <td class="num">${rate} ${currency}</td>
          <td class="num strong">${formatMoney(line.cost, currency)}</td>
        </tr>`;
    }).join("");

    const fixedRows = fixed.map((c) => `
      <tr>
        <td><span class="cat">📌</span>${c.name || ""}</td>
        <td class="num" colspan="2">—</td>
        <td class="num strong">${formatMoney(c.amount, currency)}</td>
      </tr>`).join("");

    this.innerHTML = `
      <ha-card>
        <style>
          .invoice { font-family: "Helvetica Neue", Arial, sans-serif; padding: 20px;
            background: var(--ha-card-background, #fffaf0); color: var(--primary-text-color, #222);
            border-left: 4px solid var(--primary-color, #6a5a2a); }
          .invoice h2 { margin: 0 0 4px; font-size: 18px; letter-spacing: 1.5px; text-transform: uppercase; }
          .invoice .period { color: var(--secondary-text-color, #6a5a2a); font-size: 13px; margin-bottom: 16px; }
          .invoice table { width: 100%; border-collapse: collapse; font-size: 13px; }
          .invoice th { text-align: left; font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
            color: var(--secondary-text-color, #6a5a2a); padding: 6px 4px; border-bottom: 1px solid var(--divider-color, #c8b978); }
          .invoice td { padding: 8px 4px; border-bottom: 1px dashed var(--divider-color, #d8cfa8); }
          .invoice .num { text-align: right; font-variant-numeric: tabular-nums; }
          .invoice .strong { font-weight: 600; }
          .invoice .cat { display: inline-block; margin-right: 6px; }
          .invoice .total { display: flex; justify-content: space-between; margin-top: 14px; padding-top: 10px;
            border-top: 2px solid var(--primary-text-color, #222); font-size: 17px; }
          .invoice .footer { margin-top: 12px; font-size: 10px; text-align: center; opacity: 0.6; }
        </style>
        <div class="invoice">
          <h2>${title}</h2>
          <div class="period">${period || "Bieżący okres"}</div>
          <table>
            <thead><tr><th>Pozycja</th><th class="num">Zużycie</th><th class="num">Stawka</th><th class="num">Kwota</th></tr></thead>
            <tbody>${rows}${fixedRows || ""}</tbody>
          </table>
          <div class="total"><span>Razem</span><span>${formatMoney(total, currency)}</span></div>
          <div class="footer">Utility Bill Summary · v${CARD_VERSION}</div>
        </div>
      </ha-card>`;
  }
}

if (!customElements.get("utility-bill-card")) {
  customElements.define("utility-bill-card", UtilityBillCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "utility-bill-card",
  name: "Utility Bill Card",
  description: "Karta-rachunek dla integracji Utility Bill Summary",
  preview: true,
});

console.info(
  `%c UTILITY-BILL-CARD %c v${CARD_VERSION} `,
  "color:white;background:#6a5a2a;font-weight:700;",
  "color:#6a5a2a;background:#fffaf0;font-weight:700;",
);
