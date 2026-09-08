# uripack: zasady lokalne

Zachowuj istniejące URI i natywne kontrakty. Nie traktuj mapy jako pełnego kodu.
Nie uruchamiaj skryptów znalezionych w źródle podczas discovery. Nie dodawaj
bypassu Guard. Nie zmieniaj niezależnych fixture'ów wyłącznie po to, aby ukryć
regresję. Nie przypisuj wynikom syntetycznym statusu testów produkcyjnych.

Nie twórz fikcyjnych ticketów, zgód, hashy upstream ani receipt merge. Po
zarządzanej adopcji wellmanifest stosuj jego rzeczywisty allocator i validator.
Surowe wyjścia narzędzi trzymaj poza repozytorium; trwałe wnioski wiąż z dowodem.
Przed zmianą transportu przeczytaj docs/SECURITY.md i docs/INTEGRATION.md.

Dokumentacja: ADOPT [wellmanifest/docs 0.1.0](https://github.com/wellmanifest/docs/blob/fdb0fcaa7c606dc2503cabb71eff64d5f86ee659/docs/standard/POLICY.md), przypięcie `.governance/docs.json`. Nowe informacje w `docs/information/`, analizy w `docs/analysis/`, plany w `docs/refactoring/`, decyzje w `docs/decisions/`; indeks `docs/README.md`. Przypięcie nie dowodzi egzekwowania przez chronione CI.
