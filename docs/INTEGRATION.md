# Integracja z Organism Guard i narzędziami Subactor

## Co jest gotowe

Klient `GuardBridge` wykonuje przypięty, zewnętrzny program przez stdio. Nie używa
shella ani środowiska sekretów procesu rodzica. Sprawdza integralność konfiguracji,
interpretera i skryptu adaptera przed każdym żądaniem. Weryfikuje zamknięty kształt
odpowiedzi, nonce `request_id`, dokładny hash planu, termin ważności oraz zgodność
`lease_ref` i `fencing_token` między fazami. Obcina czas i rozmiar odpowiedzi.

Jest to **nowy kontrakt integracyjny uripack**, nie udokumentowane natywne API
Organism Guard. Nie dostarczamy fikcyjnego adaptera produkcyjnego zwracającego
`allowed: true`. Testy używają wyraźnie oznaczonego mocka protokołu.

## Konfiguracja chroniona

`examples/guard-config.example.json` jest szablonem wymagającym zastąpienia
ścieżki i digesta rzeczywistym programem operatora. Konfiguracja nie może
znajdować się w źródle ani docelowym repozytorium. Umiejscowienie poza repo nie
jest samo w sobie izolacją: prawa systemowe muszą uniemożliwiać agentowi zmianę
konfiguracji, programu, zależności i magazynu lease.

`required_checks` pochodzi z chronionej konfiguracji. Request modelu może dodać
kontrole, ale nie może usunąć tej listy. `apply` wywołuje sumę obu zbiorów przed
lokalną publikacją. Sam kod wyjścia zero narzędzia nie jest wynikiem kontrolnym:
adapter musi zwrócić poprawny `uripack.check-result/v1` z hashem planu, artefaktu
oraz referencjami do rzeczywistych dowodów.

## Żądanie do adaptera

Jeden proces na jedno żądanie; UTF-8 JSON na stdin, jedna odpowiedź JSON na stdout.
`plan` występuje jako dokument tylko w fazie `admit`, w pozostałych jest `null`.
Wszystkie pola są generowane przez klienta, a adapter nadal musi traktować je
jako nieautorytatywne żądanie i sam sprawdzić ich uprawnienia.

```json
{
  "schema": "uripack.guard-request/v1",
  "request_id": "losowy-nonce",
  "action": "admit",
  "subject_sha256": "<sha256-dokladnego-planu>",
  "source_root": "/work/subactor",
  "target_root": "/work/uripack-extracted",
  "plan": "<obiekt-zgodny-z-plan.schema.json>",
  "payload": {
    "artifact_sha256": "<sha256-listy-plikow-wynikowych>",
    "staging_root": "/work/.uripack-extracted.uripack-stage-<nonce>",
    "writer_lock": "/work/.uripack-extracted.uripack-writer.lock",
    "checks": ["wellmanifest.dsl-check", "wellmanifest.governance-check", "subactor.validator-agent"],
    "mode": "extract-only"
  }
}
```

Przykład opisuje format; wartości w nawiasach nie są gotowym żądaniem wykonania.
Fazy to `admit` (zakres i lease), `tool` (narzędzie z rejestru), `publish`
(ponowna decyzja przed atomicznym ujawnieniem lokalnego katalogu), `complete`
(zapis protected receipt). `publish` nie oznacza tutaj publikacji do PyPI,
GitHub, npm ani środowiska produkcyjnego.

## Obowiązki adaptera serwerowego

Nie wolno polegać wyłącznie na kolejności wywołań klienta. Adapter musi sam
weryfikować bieżący ticket, dopuszczony zakres, aktualną politykę, aktywną
wyłączną dzierżawę, fencing token, dokładny plan i aktualność dowodów. Musi
odmawiać nieznanym identyfikatorom narzędzi oraz nieznanym natywnym schematom.
URI lub skrypt znaleziony w analizowanym repozytorium nie zostaje z tego powodu
wpisem w zaufanym rejestrze.

Dla `tool/verify-extraction` payload zawiera źródło, staging i digest artefaktu.
Kontrola powinna obejmować zarówno dotychczasowe zachowanie, jak i wydzielony
artefakt oraz wymagania domenowe. Testy trzeba wykonywać na oddzielnej kopii lub
z wejściami read-only, aby nie modyfikowały staging. Po nich klient ponownie
porównuje wszystkie pliki oraz zakres źródła.

Dla `invoke-tool` payload zawiera `tool_id`, `operation`, `domain_request` i
`domain_request_sha256`. `domain_request` zachowuje natywny schemat narzędzia.
To adapter zapewnia zgodność z tym schematem i granicą capability; uripack nie
zgaduje parametrów funkcji `execute`, CLI ani endpointów HTTP.

## Punkty integracji potwierdzone tylko przez mapę

Mapa pokazuje `autonom/autonom/repository_effect_guard.py` z
`RepositoryEffectGuard.execute` oraz `autonom/autonom/change_lease.py` z
`ChangeLeaseStore.acquire`, `transition`, `lease`. Nie zawiera pełnych sygnatur,
implementacji ani dowodów działania. Te moduły są kandydatami na integrację,
nie podstawą do wymyślenia wywołań.

Dalsze grupy: `core` — rejestr i kolizje URI; `runtime`, `connectors`,
`urirun-contract`, `urirun-flow` — kontrakty i wykonawcy; `subllm`, `supervisor`,
`coding-agent`, `repair-agent` — propozycje i ograniczone prace; `diagit`,
`doctor-agent` — diagnoza; `validator-agent`, `testkit`, `eql`, `autonomy-lab` —
niezależne kontrole; `registry`, `config`, `observability` — powiązania,
konfiguracja i dowody. `hostguard` i `guard-agent` nie zastępują autoryzacji
zmian repozytorium. Publikatory i agenty forge wymagają oddzielnego procesu.

Pełny katalog wszystkich korzeni zwraca `uripack tools`; nie ma niejawnego
„uruchom wszystko”. Każda rzeczywista kontrola otrzymuje konkretne powiązanie,
cel i uzasadnienie. Pozostałe narzędzia pozostają wykryte, nieuruchomione lub
poza zakresem danego planu.
