# Architektura implementacji

`common` obsługuje bezpieczne dane, hashe, ścieżki i czytanie plików.
`discovery` odczytuje metadane, AST Python i leksykalne wskazówki JS/TS, ale nie
importuje źródeł. `planner` kompiluje request w dokładne operacje kopiowania i
wytworzenia manifestów. `guard` jest transportem do chronionego kontrolera.
`executor` jest ograniczonym wykonawcą ekstrakcji, a `journal` przechowuje lokalny,
nieautorytatywny ślad. `governance` nie zastępuje oficjalnych validatorów.

```text
Mapa / checkout
  -> inventory + tool coverage
  -> własny, zamknięty request DSL
  -> deterministyczny plan i wybrany snapshot źródła
  -> zewnętrzny Guard: admit + scope + lease
  -> prywatny staging, niezmienione pliki i sześć warstw manifestu
  -> narzędzia niezależnej kontroli przez zaufany rejestr
  -> ponowna kontrola źródła i artefaktu
  -> zewnętrzny Guard: publish
  -> Linux atomic no-replace rename do nowego lokalnego celu
  -> zewnętrzny Guard: complete
  -> receipt EXTRACTED (bez produkcyjnego cutover)
```

`verify` jest odrębnym odczytem wyniku: sprawdza hash planu, listę plików,
zawartość i bit wykonywalności. Nie dowodzi równoważności wszystkich zachowań.
Gwarancję dotyczącą przetestowanych zachowań dostarczają osobne check results,
wiążące plan i artefakt. Demonstrują to testy wykonania obu języków.

Wyjściowe drzewo nie otrzymuje automatycznie nowego uniwersalnego instalatora.
Zachowuje natywne pakietowanie. Implementację trzeba uruchomić z odpowiedniego
korzenia pakietu w zachowanej projekcji. Ten wybór minimalizuje jednoczesne
zmiany: najpierw własność i dystrybucja definicji, później osobno rejestr,
implementacje, importy, konsumenci i produkcyjne powiązania.
