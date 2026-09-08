# Przykłady

Pliki YAML mają rzeczywisty schemat tej paczki. Ścieżki Subactor są kandydatami
z przekazanego indeksu, nie potwierdzonym stanem lokalnego checkout.
`guard-config.example.json` ma celowo zerowy digest oraz przykładową ścieżkę:
nie zadziała bez operatorowego, chronionego adaptera. Nie zamieniaj go na mock.

Działające, samowystarczalne dane Python/TypeScript tworzy `uripack demo`.
Brak `public_uris` w request oznacza brak deklaracji własności. Zachowanie plików
nie jest równoznaczne z weryfikacją dostępności usług lub importów.
