# Model zagrożeń i granice gwarancji

## Egzekwowane przez implementację

Zamknięty request nie przyjmuje poleceń shell ani autoryzacji. Plan jest
odtwarzany ze źródła przed wykonaniem i przed publikacją. Wszystkie kopiowane
pliki są porównywane przez SHA-256 i znormalizowany bit wykonywalności. Ścieżki
absolutne, `..`, symlinki i VCS/runtime-state są odrzucane lub jawnie wyłączane.
Czytanie plików korzysta z `dir_fd` i `O_NOFOLLOW`, a publikacja Linux z
`renameat2(RENAME_NOREPLACE)`. Także pusty obcy katalog nie zostanie zastąpiony.

Przenoszenie nie usuwa źródeł, nie uruchamia ich kodu i nie zmienia importów.
Testowa ekstrakcja nie jest wdrożeniem. Obcy lock nie jest „naprawiany” przez
usunięcie. Niezgodny fencing token zatrzymuje wykonanie. Wyniki narzędzi muszą
odnosić się do konkretnego planu i artefaktu.

## Wymagania zewnętrzne

**Paczka nie jest sandboxem ani kompletnym Organism Guard.** Proces mający
prawa zapisu do źródła, kontrolera i jego polityki może ominąć bibliotekę Python.
Operator musi odseparować użytkowników/uprawnienia lub kontenery, zamontować
źródło read-only, ograniczyć sieć i zasoby oraz chronić runtime, zależności,
rejestr narzędzi, konfigurację i magazyn lease. Plik SHA-256 nie tworzy zaufania.

Kontrole `source_root`/`target_root`, lokalny lock i fencing w odpowiedzi nie
są rozproszonym mechanizmem lease. Aktualność i wyłączność należą do prawdziwego
Guard. Chroniony adapter musi sprawdzać uprawnienia niezależnie od klienta.
Między ostatnią decyzją a operacją systemową pozostaje granica egzekwowania,
którą musi zabezpieczyć runtime/system operacyjny.

Skaner sekretów jest ograniczoną kontrolą popularnych formatów, NIE pełnym DLP.
Nie gwarantuje wykrycia wszystkich haseł, kluczy, kodowanych danych czy sekretów
w dokumentacji. Udostępnienie artefaktów wymaga dodatkowej kontroli sekretów.
Upstream `wellmanifest/logs` i jego podpisy/hashing nie są zaimplementowane.
Lokalny łańcuch zdarzeń wykrywa niespójność względem zachowanego punktu odniesienia,
lecz nie potwierdza autora, kompletności ani autoryzacji; cały łańcuch da się
przepisać przy dostępie do zapisu.

## Awaria i ponowienie

Nieukończony staging jest usuwany przez właściciela bieżącego wywołania, bez
usuwania obcych katalogów. Ujawniony artefakt nie jest automatycznie wycofywany
po awarii `complete`; pozostaje receipt `MATERIALIZED_PENDING_COMPLETION` i
wymagana jest chroniona rekoncyliacja. `verify` sprawdza pliki, nie nadaje zgody.

Timeout narzędzia oznacza potencjalnie nieznany skutek. Klient nie powtarza
automatycznie zlecenia. Adapter odpowiada za idempotencję i ustalenie faktycznego
stanu. Cofnięcie przyszłego routingu nie jest kompensacją już wykonanego skutku.

Integralność planu dotyczy **wybranego zakresu**, a nie całego stanu Git ani
wszystkich zależności tranzytywnych. Obca praca poza zakresem nie jest cofana.
Zachowane URI/literały i identyczne bajty nie dowodzą poprawnego działania
zewnętrznych usług ani zachowania środowiska importów.
