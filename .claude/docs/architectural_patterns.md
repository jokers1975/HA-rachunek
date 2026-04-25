# Architectural Patterns

Wzorce, które pojawiają się w wielu plikach tej integracji. Nowy kod powinien się do nich dostosowywać, a istniejące miejsca traktować jako punkty referencyjne.

## 1. Config Entry → Coordinator → Entity

HA zarządza konfiguracją jako `ConfigEntry`. Dane z entry trafiają do `UtilityBillCoordinator`, a encje (`CoordinatorEntity`) tylko odczytują gotowy `BillData`. Nie wywołujemy I/O w encjach.

- Inicjalizacja: `custom_components/utility_billing_summary/__init__.py:54` (`async_setup_entry`).
- Coordinator: `custom_components/utility_billing_summary/coordinator.py:64` (`UtilityBillCoordinator._async_update_data`).
- Encje: `custom_components/utility_billing_summary/sensor.py:38` (`_BaseBillSensor`).

**Dlaczego**: jedno źródło prawdy, łatwe testowanie, brak wyścigów między encjami.
**Jak stosować**: dodając nowy sensor, rozszerzaj `BillData` w coordinatorze i czytaj pole w encji, zamiast duplikować logikę.

## 2. `entry.data` (niezmienne) vs `entry.options` (zmienne)

Poświadczenia SMTP i tytuł instancji są w `entry.data` (wymagają pełnego reloadu przy zmianie). Listy encji, stawek, kosztów i preferencje — w `entry.options`, modyfikowane przez OptionsFlow.

- Klucze: `custom_components/utility_billing_summary/const.py:11` (`CONF_*`) vs `const.py:20` (`OPT_*`).
- Zapis options: `custom_components/utility_billing_summary/config_flow.py:270` (`async_step_save`).
- Zapis data: `config_flow.py:247` (`async_step_smtp`).
- Reload po zmianie options: `__init__.py:79` (`_async_update_listener`).

**Dlaczego**: options mogą być aktualizowane w runtime bez restartu HA; data wymaga migracji i świadomej zmiany.
**Jak stosować**: nowa ustawialna w UI opcja → `OPT_*` w `const.py` + krok w OptionsFlow. Nowa wartość wrażliwa/tożsamościowa → `entry.data` + edycja w kroku `smtp` lub własnym.

## 3. Statistics-first, state-fallback

Miesięczne zużycie pobieramy z Recorder long-term statistics. Gdy brak danych (nowa encja, brak `state_class=total*`), wracamy do delty między bieżącym stanem a zapisanym baseline'em początku miesiąca.

- Strategia: `custom_components/utility_billing_summary/statistics.py:27` (`async_monthly_sum`).
- Użycie: `custom_components/utility_billing_summary/coordinator.py:102` (`_collect_lines`).

**Dlaczego**: statistics są dokładniejsze i odporne na restarty, ale nie każdy sensor je generuje.
**Jak stosować**: nowe źródła danych powinny iść przez `async_monthly_sum`, a nie czytać `hass.states` bezpośrednio. Trzymamy baseline w `Store` per `entry_id`.

## 4. Warstwa usług oddzielona od coordinatora

Usługi HA (`services.yaml`) delegują do metod coordinatora (`async_generate_report`) i do modułu `email_report`. Schemat walidujemy przez `voluptuous`.

- Rejestracja: `custom_components/utility_billing_summary/__init__.py:109` (`_async_register_services`).
- Wywołanie: `__init__.py:148` (`_async_run_monthly_job`).
- Renderer/sender: `custom_components/utility_billing_summary/email_report.py:38` (`render_report_html`), `email_report.py:104` (`async_send_report`).

**Dlaczego**: ten sam kod obsługuje harmonogram i ręczne wywołanie usługi; renderer jest testowalny bez HA.
**Jak stosować**: nowe operacje → metoda na coordinatorze lub osobny moduł + cienki wrapper w `_async_register_services`.

## 5. i18n — PL w `translations/`, EN w kodzie

Kod, nazwy kluczy, logi, komentarze — po angielsku. Wszystko, co widzi użytkownik (tytuły kroków, opisy, opcje selectorów, nazwy encji, opisy usług), idzie przez `translations/pl.json` i `translations/en.json`.

- Klucze kroków config/options flow dopasowane do `step_id`.
- `translation_key` na selectorach: `config_flow.py:156` (`utility_category`) → `translations/pl.json:99`.
- Nazwy encji przez `_attr_translation_key`: `sensor.py:55`, mapowane w `translations/pl.json:106`.

**Dlaczego**: HA automatycznie ładuje odpowiedni język; dzięki temu można dodać kolejny język bez zmian w Pythonie.
**Jak stosować**: dodając nowy krok/label/selector, najpierw zdefiniuj klucz w obu plikach tłumaczeń, dopiero potem użyj go w Pythonie.

## 6. Serwowanie statyków Lovelace

Karta `www/utility-card.js` jest serwowana przez `async_register_static_paths` i automatycznie dodawana jako extra module przez `frontend.add_extra_js_url`. Rejestracja jest idempotentna — strażnik w `hass.data[DOMAIN]["_card_registered"]`.

- Rejestracja: `custom_components/utility_billing_summary/__init__.py:83` (`_async_register_frontend_card`).
- Stała URL/filename: `const.py:55` (`CARD_URL_PATH`, `CARD_FILENAME`).

**Dlaczego**: użytkownik nie musi ręcznie dodawać zasobu w `Ustawienia → Dashboardy → Zasoby`.
**Jak stosować**: kolejne assety frontendu kładziemy w `www/`, dorzucamy do `const.py` i rejestrujemy tym samym helperem. Unikamy podwójnej rejestracji strażnikiem w `hass.data`.

## 7. Idempotentny harmonogram miesięczny

Listener `async_track_time_change` odpala się codziennie o 09:00, a dopiero w ciele sprawdzamy `now.day == REPORT_DAY`. Flaga `OPT_AUTO_SEND` pozwala wyłączyć auto-wysyłkę bez usuwania listenera.

- Setup: `custom_components/utility_billing_summary/__init__.py:62` (`_scheduled_check`).
- Konfiguracja: `const.py:46` (`REPORT_DAY`, `REPORT_HOUR`, `REPORT_MINUTE`).

**Dlaczego**: jeden listener zamiast skomplikowanego cron-like schedulera; odporny na DST, bo `async_track_time_change` operuje na czasie lokalnym HA.
**Jak stosować**: dodając kolejne zadania okresowe, trzymaj stałe w `const.py` i delegację w `__init__.py`, a logikę generowania danych w coordinatorze.
