/**
 * Utility Bill custom card — accounting-style Lovelace card for the
 * utility_billing_summary integration. Reads a MonthTotalSensor and
 * renders: invoice table with per-line periods, month navigator, and
 * a 12-month bar chart.
 */

const CARD_VERSION = "0.3.0";

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
const PL_MONTHS_SHORT = [
  "sty", "lut", "mar", "kwi", "maj", "cze",
  "lip", "sie", "wrz", "paź", "lis", "gru",
];

function fmtMoney(value, currency) {
  const v = Number(value || 0);
  const [int, dec] = v.toFixed(2).split(".");
  const spaced = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${spaced},${dec} ${currency || ""}`.trim();
}

function fmtMonth(iso) {
  if (!iso) return "";
  const parts = iso.split("-");
  const idx = parseInt(parts[1], 10) - 1;
  return `${PL_MONTHS[idx] || ""} ${parts[0]}`;
}

function fmtPeriodRange(startIso, endIso) {
  if (!startIso || !endIso) return "";
  const [sy, sm, sd] = startIso.split("-").map(Number);
  const [ey, em, ed] = endIso.split("-").map(Number);
  if (sm === em && sy === ey) {
    return `od ${sd} do ${ed} ${PL_MONTHS[sm - 1]} ${sy}`;
  }
  return `od ${sd} ${PL_MONTHS[sm - 1]} ${sy} do ${ed} ${PL_MONTHS[em - 1]} ${ey}`;
}

function fmtCostPeriod(cost) {
  const period = fmtMonth(cost.period_month ? `${cost.period_month}-01` : "");
  const prefix = cost.billing_mode === "prepaid" ? "z góry" : "z dołu";
  return `${prefix} — za ${period}`;
}

class UtilityBillCard extends HTMLElement {
  constructor() {
    super();
    this._selectedMonth = null; // ISO YYYY-MM; null → current
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
    return 8;
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
    const history = Array.isArray(attrs.history) ? attrs.history : [];
    const currentMonth = attrs.month || (history.length ? history[history.length - 1].month + "-01" : null);
    const currentIsoMonth = (currentMonth || "").slice(0, 7);

    if (!this._selectedMonth) {
      this._selectedMonth = currentIsoMonth;
    }

    const isCurrent = this._selectedMonth === currentIsoMonth;
    const viewData = isCurrent
      ? {
          total: Number(state.state || 0),
          lines: attrs.breakdown || [],
          fixed: attrs.fixed_costs || [],
          month: currentIsoMonth,
        }
      : this._historicalView(history, attrs);

    const selectedLabel = fmtMonth(`${this._selectedMonth}-01`);
    const yearTotal = Number(attrs.year_total || 0);
    const title = this._config.title || "Rachunek za media";

    const lineRows = (viewData.lines || []).map((line) => {
      const icon = CATEGORY_ICONS[line.category] || CATEGORY_ICONS.other;
      const cons = Number(line.consumption || 0).toFixed(2);
      const hasRate = line.rate !== null && line.rate !== undefined;
      const rateCell = hasRate
        ? `${Number(line.rate).toFixed(4)} ${currency}`
        : `—`;
      const sourceMark = line.source === "energy"
        ? `<span class="src" title="Z Energy Dashboard">🔌</span>`
        : "";
      return `
        <tr>
          <td>
            <div class="name"><span class="cat">${icon}</span>${line.name || ""}${sourceMark}</div>
            <div class="period">okres: ${fmtPeriodRange(line.period_start, line.period_end)}</div>
          </td>
          <td class="num">${cons} ${line.unit || ""}</td>
          <td class="num">${rateCell}</td>
          <td class="num strong">${fmtMoney(line.cost, currency)}</td>
        </tr>`;
    }).join("");

    const fixedRows = (viewData.fixed || []).map((c) => `
      <tr>
        <td>
          <div class="name"><span class="cat">📌</span>${c.name || ""}</div>
          <div class="period">${fmtCostPeriod(c)}</div>
        </td>
        <td class="num" colspan="2">—</td>
        <td class="num strong">${fmtMoney(c.amount, currency)}</td>
      </tr>`).join("");

    const emptyRow = (!lineRows && !fixedRows)
      ? `<tr><td colspan="4" class="empty">Brak pozycji dla wybranego miesiąca.</td></tr>`
      : "";

    const chartSvg = this._renderChart(history, currency, this._selectedMonth);
    const comparisonBlock = this._renderComparison(history, viewData, currency);

    const canPrev = this._canNavigate(history, -1);
    const canNext = this._selectedMonth < currentIsoMonth;

    this.innerHTML = `
      <ha-card>
        <style>
          .wrap { font-family: "Helvetica Neue", Arial, sans-serif;
            padding: 18px 20px 20px; background: var(--ha-card-background, #fffaf0);
            color: var(--primary-text-color, #222);
            border-left: 4px solid var(--primary-color, #6a5a2a); }
          .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
          .topbar h2 { margin: 0; font-size: 17px; letter-spacing: 1.5px; text-transform: uppercase; }
          .year { font-size: 11px; letter-spacing: 1px; color: var(--secondary-text-color, #6a5a2a); }
          .year .num { color: var(--primary-text-color, #222); font-weight: 600; font-size: 13px; }
          .nav { display: flex; align-items: center; gap: 8px; justify-content: space-between;
            background: var(--secondary-background-color, #f3ecd0); padding: 6px 10px; border-radius: 4px;
            margin-bottom: 14px; }
          .nav button { background: none; border: none; cursor: pointer; padding: 4px 8px;
            font-size: 16px; color: var(--primary-text-color, #222); border-radius: 3px; }
          .nav button:hover:not(:disabled) { background: rgba(0,0,0,0.05); }
          .nav button:disabled { opacity: 0.25; cursor: not-allowed; }
          .nav .label { font-weight: 600; font-size: 14px; }
          .nav .today { font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
            color: var(--secondary-text-color, #6a5a2a); cursor: pointer; }
          table { width: 100%; border-collapse: collapse; font-size: 13px; }
          th { text-align: left; font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
            color: var(--secondary-text-color, #6a5a2a); padding: 6px 4px; border-bottom: 1.5px solid var(--primary-color, #6a5a2a); }
          td { padding: 8px 4px; border-bottom: 1px dashed var(--divider-color, #d8cfa8); vertical-align: top; }
          td.empty { text-align: center; color: var(--secondary-text-color, #6a5a2a); padding: 18px 4px; font-style: italic; }
          .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
          .strong { font-weight: 600; }
          .cat { display: inline-block; margin-right: 6px; }
          .src { margin-left: 6px; opacity: 0.7; font-size: 11px; cursor: help; }
          .name { font-weight: 500; }
          .period { font-size: 11px; color: var(--secondary-text-color, #8a7f55); margin-top: 2px; }
          .total { display: flex; justify-content: space-between; margin-top: 14px; padding-top: 10px;
            border-top: 2px solid var(--primary-text-color, #222); font-size: 17px; }
          .total .label { font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
            color: var(--secondary-text-color, #6a5a2a); font-weight: 600; align-self: center; }
          .comparison { margin-top: 14px; padding: 10px 12px; border-radius: 4px; font-size: 12px;
            border-left: 3px solid var(--primary-color, #6a5a2a); background: rgba(106,90,42,0.06); }
          .comparison.saved { border-left-color: #2a7a2a; background: rgba(42,122,42,0.08); }
          .comparison.spent { border-left-color: #b55; background: rgba(181,85,85,0.08); }
          .comparison .cmp-title { font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
            color: var(--secondary-text-color, #6a5a2a); font-weight: 600; margin-bottom: 2px; }
          .chart-box { margin-top: 18px; }
          .chart-title { font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
            color: var(--secondary-text-color, #6a5a2a); margin-bottom: 6px; }
          svg.chart { width: 100%; height: 140px; display: block; }
          svg.chart .bar { fill: var(--primary-color, #6a5a2a); opacity: 0.7; cursor: pointer; }
          svg.chart .bar.selected { opacity: 1; fill: var(--primary-text-color, #222); }
          svg.chart .bar:hover { opacity: 1; }
          svg.chart text.label { font-size: 9px; fill: var(--secondary-text-color, #6a5a2a); }
          svg.chart text.value { font-size: 9px; fill: var(--primary-text-color, #222); font-weight: 600; }
          .footer { margin-top: 10px; font-size: 10px; text-align: center; opacity: 0.55; }
        </style>
        <div class="wrap">
          <div class="topbar">
            <h2>${title}</h2>
            <div class="year">Razem w ${currentIsoMonth.slice(0, 4)}: <span class="num">${fmtMoney(yearTotal, currency)}</span></div>
          </div>
          <div class="nav">
            <button data-act="prev" ${canPrev ? "" : "disabled"} title="Poprzedni miesiąc">◀</button>
            <div class="label">${selectedLabel}</div>
            <div style="display:flex;align-items:center;gap:8px;">
              ${!isCurrent ? `<span class="today" data-act="today">dziś</span>` : ""}
              <button data-act="next" ${canNext ? "" : "disabled"} title="Następny miesiąc">▶</button>
            </div>
          </div>
          <table>
            <thead><tr><th>Pozycja</th><th class="num">Zużycie</th><th class="num">Stawka</th><th class="num">Kwota</th></tr></thead>
            <tbody>${lineRows}${fixedRows}${emptyRow}</tbody>
          </table>
          <div class="total"><span class="label">Razem do zapłaty</span><span>${fmtMoney(viewData.total, currency)}</span></div>
          ${comparisonBlock}
          <div class="chart-box">
            <div class="chart-title">Ostatnie 12 miesięcy</div>
            ${chartSvg}
          </div>
          <div class="footer">Utility Bill Summary · v${CARD_VERSION}</div>
        </div>
      </ha-card>`;

    this._wireEvents(history, currentIsoMonth);
  }

  _historicalView(history, attrs) {
    const entry = history.find((h) => h.month === this._selectedMonth);
    return {
      total: entry ? Number(entry.total) : 0,
      lines: [],
      fixed: [],
      month: this._selectedMonth,
    };
  }

  _canNavigate(history, step) {
    if (!history.length) return false;
    const sorted = history.map((h) => h.month).sort();
    const idx = sorted.indexOf(this._selectedMonth);
    if (step < 0) return idx > 0;
    return idx >= 0 && idx < sorted.length - 1;
  }

  _renderComparison(history, viewData, currency) {
    if (!history.length) return "";
    const sorted = [...history].sort((a, b) => a.month.localeCompare(b.month));
    const idx = sorted.findIndex((h) => h.month === this._selectedMonth);
    if (idx <= 0) return "";
    const prev = sorted[idx - 1];
    const diff = Number(viewData.total) - Number(prev.total);
    if (!prev.total) return "";
    const absDiff = Math.abs(diff);
    let cls = "equal";
    let sentence = `Wydatki są takie same jak w miesiącu ${fmtMonth(prev.month + "-01")}.`;
    if (diff < -0.005) {
      cls = "saved";
      sentence = `Zaoszczędziłeś ${fmtMoney(absDiff, currency)} w porównaniu z miesiącem ${fmtMonth(prev.month + "-01")}.`;
    } else if (diff > 0.005) {
      cls = "spent";
      sentence = `Wydałeś o ${fmtMoney(absDiff, currency)} więcej niż w miesiącu ${fmtMonth(prev.month + "-01")}.`;
    }
    return `<div class="comparison ${cls}">
      <div class="cmp-title">Porównanie z poprzednim miesiącem</div>
      <div>${sentence}</div>
    </div>`;
  }

  _renderChart(history, currency, selected) {
    if (!history.length) return `<div style="color:var(--secondary-text-color);font-size:12px;">Brak danych historycznych.</div>`;
    const width = 600;
    const height = 140;
    const padTop = 14;
    const padBottom = 22;
    const max = Math.max(...history.map((h) => Number(h.total) || 0), 1);
    const barW = width / history.length;
    const chartH = height - padTop - padBottom;

    const bars = history.map((h, i) => {
      const total = Number(h.total) || 0;
      const barHeight = max > 0 ? (total / max) * chartH : 0;
      const x = i * barW + 4;
      const y = padTop + (chartH - barHeight);
      const w = barW - 8;
      const selCls = h.month === selected ? "selected" : "";
      const [, mo] = h.month.split("-");
      const label = PL_MONTHS_SHORT[parseInt(mo, 10) - 1] || "";
      return `
        <g>
          <rect class="bar ${selCls}" data-month="${h.month}"
            x="${x}" y="${y}" width="${w}" height="${barHeight}" rx="2"></rect>
          <text class="label" x="${x + w / 2}" y="${height - 8}" text-anchor="middle">${label}</text>
          ${h.month === selected ? `<text class="value" x="${x + w / 2}" y="${y - 3}" text-anchor="middle">${Math.round(total)}</text>` : ""}
        </g>`;
    }).join("");

    return `<svg class="chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${bars}</svg>`;
  }

  _wireEvents(history, currentIsoMonth) {
    const nav = this.querySelector(".nav");
    if (nav) {
      nav.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-act]");
        if (!btn) return;
        const sorted = [...history].map((h) => h.month).sort();
        const idx = sorted.indexOf(this._selectedMonth);
        const act = btn.dataset.act;
        if (act === "prev" && idx > 0) this._selectedMonth = sorted[idx - 1];
        else if (act === "next" && idx < sorted.length - 1) this._selectedMonth = sorted[idx + 1];
        else if (act === "today") this._selectedMonth = currentIsoMonth;
        this._render();
      });
    }
    this.querySelectorAll("svg.chart .bar").forEach((rect) => {
      rect.addEventListener("click", () => {
        this._selectedMonth = rect.dataset.month;
        this._render();
      });
    });
  }
}

if (!customElements.get("utility-bill-card")) {
  customElements.define("utility-bill-card", UtilityBillCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === "utility-bill-card")) {
  window.customCards.push({
    type: "utility-bill-card",
    name: "Utility Bill Card",
    description: "Karta-rachunek dla integracji Utility Bill Summary",
    preview: true,
  });
}

console.info(
  `%c UTILITY-BILL-CARD %c v${CARD_VERSION} `,
  "color:white;background:#6a5a2a;font-weight:700;",
  "color:#6a5a2a;background:#fffaf0;font-weight:700;",
);
