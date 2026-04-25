# CLAUDE.md

## Przegląd projektu

Utility Bill Summary — niestandardowa integracja Home Assistant dystrybuowana przez HACS (custom repository). Agreguje zużycie mediów z wybranych encji według stawek, dolicza stałe koszty miesięczne, wystawia sensory kosztów, renderuje kartę Lovelace w stylu faktury i 1. dnia miesiąca o 09:00 wysyła e-mailem podsumowanie za poprzedni miesiąc.

## Stack technologiczny

- **Runtime**: Home Assistant ≥ 2024.4, Python 3.12, w pełni async (`async_setup_entry`, `async/await`).
- **HA API**: `DataUpdateCoordinator`, `ConfigFlow`/`OptionsFlow`, `Recorder statistics`, `frontend.add_extra_js_url`, `http.StaticPathConfig`, `async_track_time_change`.
- **Zewnętrzne zależności**: `aiosmtplib` (async SMTP; deklarowane w `manifest.json`).
- **Frontend**: vanilla custom element (`HTMLElement`) bez bundlera, rejestrowany przez `customElements.define`.
- **Dystrybucja**: HACS (`hacs.json`).
- **Tłumaczenia**: `translations/pl.json` (PL UI), `translations/en.json` (EN UI). Kod, nazwy zmiennych i komentarze — angielski.

## Kluczowe katalogi

| Ścieżka | Przeznaczenie |
|---|---|
| `custom_components/utility_billing_summary/__init__.py` | Setup/unload, rejestracja usług, harmonogram, serwowanie karty. |
| `custom_components/utility_billing_summary/coordinator.py` | `UtilityBillCoordinator` — agregacja miesięczna/roczna, generacja raportu. |
| `custom_components/utility_billing_summary/config_flow.py` | Initial ConfigFlow (SMTP) + `OptionsFlowHandler` (encje, koszty stałe, odbiorcy, preferencje). |
| `custom_components/utility_billing_summary/sensor.py` | `MonthTotalSensor`, `LastMonthTotalSensor`, `YearTotalSensor`, `UtilityCostSensor`. |
| `custom_components/utility_billing_summary/statistics.py` | Statistics-first/state-fallback dla miesięcznego zużycia. |
| `custom_components/utility_billing_summary/email_report.py` | Render HTML faktury + async SMTP send. |
| `custom_components/utility_billing_summary/const.py` | `DOMAIN`, klucze konfiguracji, domyślne wartości. |
| `custom_components/utility_billing_summary/services.yaml` | Opisy usług dla UI HA. |
| `custom_components/utility_billing_summary/translations/` | Pliki tłumaczeń UI. |
| `www/utility-card.js` | Custom card Lovelace. |
| `hacs.json`, `manifest.json` | Metadane HACS i HA. |

## Najważniejsze komendy

```bash
# Walidacja składni Pythona (HA nie musi być zainstalowany)
python -m py_compile custom_components/utility_billing_summary/*.py

# Walidacja wszystkich plików JSON
python -c "import json,glob; [json.load(open(p)) for p in glob.glob('**/*.json', recursive=True)]"

# Lint (opcjonalnie)
ruff check custom_components/
ruff format --check custom_components/

# Testy (opcjonalnie — nie dołączone w tym wydaniu)
pytest tests/
```

## Manualna weryfikacja w HA

1. Skopiuj repo do katalogu HA lub dodaj jako **HACS → Custom Repository** (Integration).
2. Zrestartuj HA, dodaj integrację przez UI, uzupełnij SMTP.
3. W „Konfiguruj” dodaj przynajmniej jedną encję, stawkę, kosztu stały i odbiorcę.
4. Uruchom `utility_billing_summary.generate_preview` i sprawdź HTML.
5. Uruchom `utility_billing_summary.send_monthly_report` i zweryfikuj e-mail.
6. Dodaj kartę `custom:utility-bill-card` z encją `sensor.rachunek_miesieczny`.

## Dodatkowa dokumentacja

- [Architectural patterns](.claude/docs/architectural_patterns.md) — wzorce wielokrotnego użytku: cykl Config Entry → Coordinator → Entity, podział `entry.data` vs `entry.options`, statistics-first/state-fallback, separacja warstwy usług, i18n, serwowanie statyków Lovelace.
