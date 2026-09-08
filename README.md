# uripack — refaktoryzacja procesów URI

Nowość w rozwoju: [samodzielne usługi URI z Dockerem](docs/information/standalone-uri-services.md) — jawne profile Python/Node w kontrakcie v2, przykłady i granice walidacji.

**Paczka Python:** `uripack-refactor` · **CLI:** `uripack` · **wersja:** `0.1.0a1`.

Działająca pierwsza faza refaktoryzacji: statyczna inwentaryzacja, deterministyczny
plan, ekstrakcja całych plików/paczek do wielowarstwowego katalogu `uripack`,
niezależne sprawdzenie integralności i kontrolowane wywołania narzędzi przez
zewnętrzną granicę Organism Guard. Oryginalne repozytorium nie jest modyfikowane.

**Nie jest to deklaracja zakończenia migracji Subactor.** Dostępne były mapa
`code2llm` z 5 września 2026 r. oraz część publicznej dokumentacji standardów,
nie pełny checkout i działające usługi Subactor. Native API Organism Guard nie
zostało odgadnięte z indeksu symboli. Dostarczony transport wymaga osobnego,
chronionego adaptera do rzeczywistej instalacji. Bez niego `apply` odmawia pracy.

## Uruchomienie

Python 3.11 lub nowszy; ekstrakcja `apply` wymaga Linux z `O_NOFOLLOW` i
`renameat2(RENAME_NOREPLACE)`. Node.js i `tsc` są potrzebne do demonstracji oraz
testów TypeScript, nie do samej inwentaryzacji czy kompilacji planu.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uripack --help
pytest -q
uripack demo --out-dir /tmp/uripack-demo-example
```

Z gotowego koła:

```bash
python -m pip install ./uripack_refactor-0.1.0a1-py3-none-any.whl
uripack --version
```

Instalacja rozwiązuje dwie zależności: `jsonschema` i `PyYAML`. Paczka nie instaluje
Subactor, nie uruchamia skryptów znalezionych w `package.json` i nie pobiera
narzędzi w trakcie refaktoryzacji. Kontenery i zależności narzędzi pozostają
odpowiedzialnością chronionego środowiska wykonawczego.

## Praca na lokalnym Subactor

Wskaż prawdziwy checkout, nie samą mapę. `/work/evidence` musi być poza źródłem
i nowym celem. Docelowy `/work/uripack-extracted` nie może już istnieć.

```bash
uripack tools --root /work/subactor --out /work/evidence/tools.json
uripack inventory --root /work/subactor \
  --include platform/config/process-packs/problem-reaction-observer \
  --out /work/evidence/inventory.json
uripack adoption-audit --root /work/subactor \
  --out /work/evidence/adoption.json
uripack validate-request examples/subactor-extract.yaml
uripack plan --request examples/subactor-extract.yaml \
  --source /work/subactor --target /work/uripack-extracted \
  --out /work/evidence/plan.json
```

`examples/subactor-extract.yaml` jest przykładowym zakresem do przeglądu, a nie
potwierdzeniem dostępności plików w Twoim bieżącym checkout. URI podawane jako
`public_uris` muszą rzeczywiście występować w wybranych plikach. Pominięcie tego
pola oznacza zachowanie bajtów i zebranie kandydatów, **nie potwierdzenie własności URI**.

Po skonfigurowaniu chronionej integracji opisanej w `docs/INTEGRATION.md`:

```bash
uripack apply --plan /work/evidence/plan.json \
  --guard-config /etc/organism/uripack-bridge.json \
  --out /work/evidence/extraction.json
uripack verify --plan /work/evidence/plan.json \
  --out /work/evidence/verification.json
```

Nie istnieje opcja `--force`, `--unsafe`, `--skip-guard` ani `--demo-guard` dla
`apply`. Zmienione źródło wymaga nowego planu. Istniejący obcy cel nie jest
nadpisywany. Ponowne wywołanie dla ukończonego, identycznego artefaktu sprawdza
jego zawartość, ale nie powtarza narzędzi i nie odnawia uprawnień.

## Wielowarstwowy wynik

```text
uripack-extracted/
├── uripack.json
├── uripack.lock.json
├── compatibility/source-aliases.proposed.json
├── packs/<unit>/
│   ├── uripack.json
│   ├── uri-baseline.json
│   └── tree/<oryginalna-ścieżka>/...
└── .uripack/receipt.json
```

Manifest paczki ma sześć warstw: tożsamość URI, zachowane kontrakty,
implementacje Python/TypeScript/JavaScript, zależności, pochodzenie oraz
weryfikację. `tree/` zachowuje względny układ wybranych plików od korzenia
źródła. Natywne `pyproject.toml`, `package.json` i locki pozostają niezmienione.
Nie następuje automatyczne rozwiązanie zależności ani konwersja starego formatu
na `poa.process/v1`.

`depends_on` między jednostkami jest sprawdzanym grafem deklaracji. Nie ustawia
`PYTHONPATH`, nie konfiguruje workspaces npm i nie naprawia importów między
jednostkami. W pierwszej migracji wybieraj kompletne paczki lub domknięty zakres;
instalowalność i zachowanie muszą potwierdzić niezależne narzędzia.

## Narzędzia `subactor/*`

Dostarczony indeks obejmuje wszystkie **102 korzenie katalogów i 23 070 wpisów
modułów** z przekazanej mapy. Korzeń nie musi być narzędziem. `tools` pokazuje
każdy korzeń, jego rolę oraz poziom dowodu: indeks albo lokalne metadane. Żaden
nie otrzymuje automatycznie statusu „uruchomiony” lub „zaufany”.

`invoke-tool` pozwala użyć dowolnego narzędzia z rejestru chronionego adaptera,
bez dodawania jego klienta do tej paczki. Request zachowuje natywny schemat DSL:

```bash
uripack invoke-tool --plan /work/evidence/plan.json \
  --guard-config /etc/organism/uripack-bridge.json \
  --tool-id subactor.diagit --operation inspect \
  --request /work/evidence/native-diagit-request.json \
  --out /work/evidence/diagit-response.json
```

Identyfikatory powiązań są wybierane przez operatora; powyższe nie ustanawia
nowego natywnego API `diagit`. Adapter musi zweryfikować rzeczywisty schemat
narzędzia, rozwiązać jego punkt wejścia i wykonać operację pod prawdziwą polityką
Guard. Odebrana odpowiedź nie jest automatycznie interpretowana jako sukces
domenowy. Szczegółowe role i braki: `docs/INTEGRATION.md` oraz `uripack tools`.

## LLM, DSL i governance

`llm-envelope` przygotowuje metadane i zamknięty schemat odpowiedzi dla `subllm`
lub innej istniejącej bramki. Odpowiedź może mieć wyłącznie `operation: plan`.
Polecenie **nie wykonuje połączenia LLM**. Wywołanie modelu można przekazać przez
`invoke-tool` do skonfigurowanego, chronionego adaptera z natywnym requestem.

```bash
uripack llm-envelope --inventory /work/evidence/inventory.json \
  --intent 'Wydziel istniejący proces bez zmiany URI i zachowania' \
  --out /work/evidence/llm-envelope.json
```

Profile `uripack.*` są własnymi kontraktami tego projektu, nie podszywają się pod
schematy `wellmanifest/dsl`, POA ani `wellmanifest/logs`. Dołączono gramatykę GBNF
wspomagającą generowanie; jej egzekwowanie po stronie dostawcy LLM nie zostało
przetestowane. Walidacja JSON Schema i preconditions pozostają obowiązkowe.

`adoption-audit` jedynie sprawdza pliki adopcji. Nie tworzy fikcyjnego locka,
zgody, ticketu ani receipt merge. Oficjalną adopcję, przydział ticketów,
worktree i walidację należy delegować do przypiętych narzędzi standardu.
Zakres odczytanych źródeł i braki są opisane w `docs/CONFORMANCE.md`.

## Testy i ograniczenia

`demo` rzeczywiście kompiluje TypeScript, wykonuje Python i wynikowy JavaScript,
porównuje stare/nowe wykonania oraz oba języki. Używa wyłącznie własnych danych
testowych i jawnie syntetycznego Guard. Nie jest testem usług Subactor,
produkcyjnego Guard, LLM, Dockera ani wdrożenia.

Niezaimplementowane: automatyczne przepisywanie dowolnych funkcji/importów,
przełączenie produkcyjnych powiązań, usuwanie starego kodu, publikacja PyPI/npm,
Git commit/push/merge, silnik kontenerowy i natywna implementacja decyzji Organism
Guard. Transport do tych możliwości istnieje, ale zgodność natywnych adapterów
wymaga kodu Twojej instalacji i niezależnych testów.

Zobacz `docs/SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/CONFORMANCE.md` oraz
`docs/VALIDATION.md`. Kod można opublikować jako repozytorium `uripack`; ta paczka
nie tworzy zdalnego repozytorium ani nie publikuje niczego automatycznie.
