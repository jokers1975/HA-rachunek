# Utility Bill Summary

Integracja Home Assistant, która agreguje zużycie mediów, wylicza koszty według skonfigurowanych stawek i raz w miesiącu wysyła graficzny rachunek e-mailem. Zawiera również niestandardową kartę Lovelace w stylu papierowej faktury.

## Funkcje

- Dowolna liczba encji zużycia (prąd, gaz, woda, ogrzewanie, inne) z indywidualnymi stawkami i jednostkami.
- Stałe koszty miesięczne (abonamenty, opłaty stałe).
- Sensory: bieżący miesiąc, poprzedni miesiąc, suma roczna oraz per media.
- Preferowane źródło danych: Recorder long-term statistics, z automatycznym fallbackiem do delty stanu encji.
- Wbudowany harmonogram: 1. dnia każdego miesiąca o 09:00 lokalnie integracja wysyła podsumowanie za poprzedni miesiąc.
- Usługi HA: `send_monthly_report`, `generate_preview`.
- Karta Lovelace `utility-bill-card` z układem przypominającym fakturę.

## Instalacja przez HACS (Custom Repository)

1. W HA otwórz **HACS → Integracje → menu (⋮) → Niestandardowe repozytoria**.
2. Wklej URL `https://github.com/jokers1975/HA-rachunek`, wybierz kategorię **Integration** i zapisz.
3. Znajdź pozycję „Utility Bill Summary” na liście HACS i zainstaluj.
4. Zrestartuj Home Assistanta.

[![HACS Validate](https://github.com/jokers1975/HA-rachunek/actions/workflows/validate.yml/badge.svg)](https://github.com/jokers1975/HA-rachunek/actions/workflows/validate.yml)
[![Lint](https://github.com/jokers1975/HA-rachunek/actions/workflows/lint.yml/badge.svg)](https://github.com/jokers1975/HA-rachunek/actions/workflows/lint.yml)

## Konfiguracja

1. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Utility Bill Summary**.
2. Podaj nazwę instancji oraz dane serwera SMTP (host, port, użytkownik, hasło, TLS, adres nadawcy).
3. Po utworzeniu integracji kliknij **Konfiguruj** na karcie instancji, aby:
   - dodać encje zużycia ze stawką, jednostką i kategorią,
   - zdefiniować koszty stałe,
   - podać odbiorców raportu (adresy oddzielone przecinkami),
   - zmienić walutę lub wyłączyć automatyczną wysyłkę.

> Wskazówka: aby dane miesięczne były w pełni dokładne, wybieraj encje z `state_class=total` lub `total_increasing`, które trafiają do Recorder long-term statistics. Jeśli statystyki nie są dostępne, integracja zapamiętuje stan na początku miesiąca i liczy przyrost.

## Karta Lovelace

Integracja serwuje plik karty pod adresem `/utility_billing_summary/utility-card.js` i rejestruje ją automatycznie (`extra_module_url`). Po restarcie HA dodaj kartę ręcznie w interfejsie:

```yaml
type: custom:utility-bill-card
entity: sensor.rachunek_miesieczny
title: Rachunek domowy
```

## Usługi

`utility_billing_summary.send_monthly_report` — generuje HTML i wysyła e-mail.

```yaml
service: utility_billing_summary.send_monthly_report
data:
  recipients:
    - biuro@example.com
  month: "2026-03"   # opcjonalnie — domyślnie poprzedni miesiąc
```

`utility_billing_summary.generate_preview` — zwraca HTML raportu bez wysyłki.

```yaml
service: utility_billing_summary.generate_preview
data:
  month: "2026-03"
```

## Wymagania

- Home Assistant 2024.4 lub nowszy.
- Aktywna integracja Recorder (domyślnie włączona).
- Serwer SMTP z uwierzytelnianiem.

## Licencja

MIT.
