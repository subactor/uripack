# Źródła i status zgodności

Odczyt źródeł: 8 września 2026 r. Obserwacje mutable `main` nie są pinami
niezmiennych commitów. Nie opublikowano fikcyjnego locka adopcji.

| Źródło | Co rzeczywiście odczytano | Co zastosowano | Co nie jest potwierdzone |
|---|---|---|---|
| wellmanifest/dsl | README, VERSION `0.1.0-dev`, listy `spec/`, `schemas/`, `src/` | oddzielny profil domenowy, wspólne kontrakty, request-only boundary, testy deterministyczne | pełna zgodność z DSL_STANDARD i dsl-manifest.schema, uruchomienie dsl_check |
| wellmanifest/new-project | README, VERSION `0.20.11`, CONTRIBUTING.md, manifest.schema.json | rozdzielenie planu/autoryzacji/skutków, brak fałszywych zgód, ticketów i locków; materialny kod i testy | pełna adopcja immutable revision, oficjalne governance gate, worktree/ticket allocation |
| mapa Subactor | sekcja modułów i indeks symboli z 2026-09-05 | katalog wszystkich 102 korzeni i 23 070 modułów, kandydaci integracji | zawartość kodu i manifestów, dostępność usług, ich zachowanie |
| POA / logs | kontekst wcześniejszej rozmowy; bez nowej walidacji implementacyjnej | pozostawienie natywnych formatów i osobnych granic | konwersja lub wire-conformance; brak takiej deklaracji |

README `dsl` mówi o bootstrapie i planowaniu, ale katalogi pokazują również
plik `src/dsl_check.py`. To nie wystarcza do ustalenia kompletności implementacji.
Pobranie treści `spec/DSL_STANDARD.md`, `schemas/dsl-manifest.schema.json` i
`src/dsl_check.py` nie powiodło się w tej sesji. Nie zastąpiono ich wymyśloną
specyfikacją. Lokalne kontrakty mają przestrzeń nazw `uripack.*`.

`CONTRIBUTING.md` rozróżnia normatywny tekst policy DSL od wykonywalnej walidacji,
odrębne rejestry operations/events/errors/models, kontrolowane URI Process/CQRS,
ograniczoną intencję, osobny worktree/lease oraz protected receipt. Uripack nie
interpretuje prozy `DO/FORBID` jako kodu i nie próbuje regenerować zarządzanych
skryptów z opisów. Rejestry tego repo mają własny format i nie są oznaczone jako
przeszłe oficjalny validator `domainContracts.mode=cqrs`.

W pełnej instalacji operator powinien uruchomić oficjalną, przypiętą adopcję
(np. opisane przez upstream `goal governance adopt --target-root ...
--source-revision <FULL_PUBLISHED_SHA>`), przydzielić ticket zarządzanym
allocatorem i przypiąć właściwe walidatory w chronionym adapterze. Nie ręcznie
tworzyć `project/ticket-001` ani liczyć rzekomego oficjalnego locka w uripack.

Lokalny profil kanonizacji `uripack.c14n/v1` sortuje klucze według UTF-16,
stosuje JSON bez dodatkowych białych znaków i dopuszcza liczby o wartościach
całkowitych w zakresie bezpiecznych liczb JavaScript. `1.0` jest kanonizowane
do `1`; liczby ułamkowe, nieskończoności i niesparowane surrogate są odrzucane.
Profil ma testy Python/TypeScript. Nie jest deklaracją pełnej implementacji
RFC8785 ani profilu hashowania `wellmanifest/logs`.

## Referencje

- https://github.com/wellmanifest/dsl
- https://github.com/wellmanifest/dsl/tree/main/spec
- https://github.com/wellmanifest/dsl/tree/main/schemas
- https://github.com/wellmanifest/dsl/tree/main/src
- https://raw.githubusercontent.com/wellmanifest/dsl/main/VERSION
- https://github.com/wellmanifest/new-project
- https://raw.githubusercontent.com/wellmanifest/new-project/main/CONTRIBUTING.md
- https://raw.githubusercontent.com/wellmanifest/new-project/main/governance/manifest.schema.json
- https://raw.githubusercontent.com/wellmanifest/new-project/main/VERSION
- Załączona mapa `map.toon(9).yaml`, producent `code2llm`; jej SHA-256 znajduje się
  w `src/uripack_refactor/resources/subactor-map-index.json`.
