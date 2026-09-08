# Walidacja

```bash
python -m pytest -q
python -m coverage run --source=uripack_refactor -m pytest -q
python -m coverage report
uripack demo --out-dir /tmp/uripack-demo-unique
```

Testy obejmują ścisły request JSON/YAML, duplikaty i nieznane pola, path traversal,
symlinki, podstawowy filtr sekretów, kolizje URI i plików, cykle, ograniczenia,
zmiany źródeł po planowaniu, stare lease/fencing, brak nadpisywania obcego celu,
modyfikację artefaktu przez kontrolę, utratę potwierdzenia po materializacji,
idempotentny odczyt zakończonego wyniku, rzeczywisty transport stdio z mockiem
kontrolera oraz Python/TypeScript schema/canonical conformance.

E2E kompiluje rzeczywisty fixture TypeScript przez `tsc`, uruchamia oba języki
przed i po ekstrakcji oraz porównuje trzy przypadki danych, w tym Unicode.
Jest to **test syntetycznego repozytorium**, nie usług Subactor lub natywnego
Organism Guard. Test komunikacji z adapterem nie weryfikuje jego produkcyjnej
polityki. Nie wykonano wywołań LLM, Docker, PyPI/npm ani Git push/merge.

Wyniki bieżącego wykonania i środowisko są dostarczane w osobnym katalogu
walidacji/release, poza kodem źródłowym. Liczba testów nie jest dowodem pokrycia
wszystkich scenariuszy ataku ani całkowitej równoważności zachowania.
