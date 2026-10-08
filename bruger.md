# Brugervejledning - 360APIWrapper

Denne guide tager dig fra en helt tom maskine til at kunne søge, oprette og
slå sagstyper op i Public 360° via `Public360Client`. Den er tænkt som en
praktisk "gør sådan"-vejledning - for det fulde authentikerings-flow i
detaljer, se [AUTHENTICATE.md](AUTHENTICATE.md), og for den korte reference,
se [README.md](README.md).

## Indhold

- [1. Forudsætninger](#1-forudsætninger)
- [2. Hent projektet og installér afhængigheder](#2-hent-projektet-og-installér-afhængigheder)
- [3. Sæt authentikering op (én gang)](#3-sæt-authentikering-op-én-gang)
- [4. Importér og opret klienten](#4-importér-og-opret-klienten)
- [5. Tjek forbindelsen med `ping()`](#5-tjek-forbindelsen-med-ping)
- [6. Søg sager med `get_cases()`](#6-søg-sager-med-get_cases)
- [7. Opret en sag med `create_case()`](#7-opret-en-sag-med-create_case)
- [8. Sagstyper - `CaseType`-enum'et](#8-sagstyper---casetype-enum\'et)
- [9. Sagsstatusser - `CaseStatus`-enum'et](#9-sagsstatusser---casestatus-enum\'et)
- [10. Slå kodetabeller op med `get_code_table_rows()`](#10-slå-kodetabeller-op-med-get_code_table_rows)
- [11. Generelle API-kald med `get()`/`post()`](#11-generelle-api-kald-med-getpost)
- [12. Scripts til automatisk drift](#12-scripts-til-automatisk-drift)
- [13. Sikkerhed](#13-sikkerhed)

## 1. Forudsætninger

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** installeret (bruges til at
  installere afhængigheder og køre scripts)
- Adgang til en **FK-servicebruger**, der kan logge ind via FK
  Adgangsstyring (SAML)
- `realm_url` og `client_id` udleveret af Tieto (jeres 360°-kontakt) - se
  afsnit 3

## 2. Hent projektet og installér afhængigheder

```bash
git clone <repo-url> 360APIWrapper
cd 360APIWrapper
uv sync
```

`uv sync` læser `pyproject.toml`/`uv.lock` og installerer alt, der skal
bruges (bl.a. `requests`), i et lokalt `.venv`. Kør altid scripts med
`uv run`, fx:

```bash
uv run python test.py
```

Hvis du selv skal tilføje en ny afhængighed til projektet (ikke
nødvendigt for at komme i gang), bruges:

```bash
uv add <pakke-navn>
```

## 3. Sæt authentikering op (én gang)

Før klienten kan bruges, skal I have:

| Værdi | Hvorfra | Eksempel |
|---|---|---|
| `realm_url` | Fra Tieto | `https://keycloak.360online.com/realms/<customer-realm>` |
| `client_id` | Fra Tieto | Bootstrap/runtime client-id oprettet til jeres integration |
| `tenant_host` | I bestemmer selv | `kommune.public360online.com` |
| `token_storage_path` | I bestemmer selv | `./fk-api-offline-token.local.json` |

Der er **intet brugernavn/kodeord** at skrive ind i koden. Det eneste
login er ét interaktivt browser-login, som en FK-servicebruger udfører
**én gang**:

```bash
uv run python scripts/bootstrap_once.py
```

Dette åbner en browser, I logger ind via FK Adgangsstyring, og et
offline token gemmes på disk. Alt det efterfølgende (token-fornyelse,
Bearer-headers, retries) sker automatisk - I skal ikke logge ind igen,
medmindre tokenet bliver tilbagekaldt eller udløber (se afsnit 9-10 i
[AUTHENTICATE.md](AUTHENTICATE.md)).

## 4. Importér og opret klienten

```python
from src.public360_client import Public360Client

client = Public360Client(
    realm_url="https://keycloak.360online.com/realms/<customer-realm>",
    client_id="<bootstrap-client-id>",
    tenant_host="<kommune>.public360online.com",
    token_storage_path="./fk-api-offline-token.local.json",
)
```

Dette sender intet over netværket endnu - det klargør bare klienten med
de værdier, der skal bruges ved senere kald. Alle metoder herunder
kaldes på dette `client`-objekt.

## 5. Tjek forbindelsen med `ping()`

Hvert service-endpoint i 360° har en `Ping()`-metode, der bekræfter at I
har adgang, at tjenesten er korrekt installeret, og at jeres bruger
mindst har læserettigheder. Den kaster en fejl ved problemer og
returnerer intet ved succes:

```python
client.ping()                       # pinger CaseService (default)
client.ping(service="SupportService")  # pinger et andet service-endpoint
```

> Bemærk: Hvilke services/metoder der er tilladt, afhænger af
> endpoint-konfigurationen i 360° web admin. Får du `403 Forbidden`, er
> den pågældende service/metode ikke slået til for jeres klient - kontakt
> jeres 360°-administrator.

## 6. Søg sager med `get_cases()`

```python
from src.public360_client import CaseType

result = client.get_cases(
    cpr_number="0101001234",        # borgerens CPR-nummer
    case_type=CaseType.CITIZEN_CASE,  # sagstype
)

for case in result["Cases"]:
    print(case["CaseNumber"], case["Title"])

print("Antal hits:", result["TotalCount"])
```

| Parameter | Beskrivelse |
|---|---|
| `cpr_number` | Borgerens CPR-nummer. Sendes som `ContactReferenceNumber`. |
| `case_type` | Sagstype - kodeværdi, `"recno:<tal>"`, eller et `CaseType`-medlem (se afsnit 8). |
| `max_returned_cases` | Maks. antal sager der returneres. Default `100`. |
| `page` / `sort_criterion` | Paginering - brug altid sammen. |
| `**extra_query` | Alle andre `GetCasesQuery`-felter (fx `Recno`, `CaseNumber`, `ArchiveCode`) sendes med uændret. |

`get_cases()` kræver mindst ét søgekriterie og kaster en `ValueError`,
hvis intet er angivet.

## 7. Opret en sag med `create_case()`

```python
from src.public360_client import CaseStatus, CaseType

result = client.create_case(
    title="Ansøgning om byggetilladelse",
    case_type=CaseType.BOM_BYGGESAG,
    status=CaseStatus.B1_0,  # "1.0 Screening - Sag modtaget, afventer screening"
    access_group="Public",
)

print(result["CaseNumber"], result["Recno"])
```

> Angiver I ikke `status`, bruger 360° en standardstatus (recno 5,
> `CaseStatus.B`), som ikke nødvendigvis er gyldig for den valgte
> `case_type` - 360° afviser da kaldet med *"The selected Case Status is
> not valid for the Case Type"*. Vælg altid en status, der matcher
> sagstypens workflow (se afsnit 9); eksemplet ovenfor bruger `B1_0`,
> fordi de `B*`-kodede statusser (`B1_0` ... `B7_0`) er workflowtrinnene
> for netop `BOM_BYGGESAG`.

| Parameter | Beskrivelse |
|---|---|
| `title` | **Påkrævet.** Sagens titel/beskrivelse. |
| `unofficial_title` | Uofficiel titel - bruger `title` hvis ikke sat. |
| `case_type` | Sagstype, fx et `CaseType`-medlem (se afsnit 8). |
| `status` | Sagsstatus - kodeværdi, recno, eller et `CaseStatus`-medlem (fx `CaseStatus.B` = "Under behandling", se afsnit 9). Sættes den ikke, bruger 360° en standardstatus, som ikke nødvendigvis er gyldig for jeres `case_type` (se advarsel i afsnit 9). |
| `access_code` / `access_group` | Adgangskode/-gruppe for sagen. |
| `journal_unit` / `sub_archive` | Journalenhed/underarkiv. |
| `responsible_person_id_number` / `_recno` / `_email` / `_user_id` | Angiv **kun én** af disse til at identificere den ansvarlige sagsbehandler. |
| `**extra_fields` | Alle andre `CreateCaseParameter`-felter (fx `ArchiveCodes`, `Contacts`, `Keywords`, `Category`, `Project`, `Remarks`). |

Svaret er et `CaseOperationResult`: `Recno`, `CaseNumber`, `UID` ved
succes, eller `ErrorMessage`/`ErrorDetails` ved fejl.

## 8. Sagstyper - `CaseType`-enum'et

Sagstyper er tenant-specifikke og kan ikke gættes - de afhænger af,
hvilken opsætning jeres 360°-installation har. `CaseType` i
`src/public360_client.py` indeholder de **aktive** sagstyper, som faktisk
findes i Næstveds produktionsmiljø (hentet live via
`get_code_table_rows()`, se afsnit 9):

```python
from src.public360_client import CaseType

CaseType.ADMINISTRATIVE_CASE   # "recno:300001"
CaseType.EMPLOYEE_CASE         # "recno:300002"
CaseType.CITIZEN_CASE          # "recno:300003"
CaseType.GEO_CASE              # "recno:300004"
CaseType.BOM_BYGGESAG           # "recno:500097"
# ... se klassen for alle 21 medlemmer
```

Værdierne bruger `"recno:<tal>"` i stedet for kodenavnet, fordi to
rækker i kodetabellen deler samme kodenavn (`"BOM Byggesag"`) med
forskellige recno'er - recno er altid entydigt.

> Bemærk: Den generiske standardværdi fra SIF-dokumentationen (recno 2,
> `"Sak"`/`"Case"`) er **udløbet** i Næstveds tenant og er derfor ikke
> med i listen. Bruger I et andet 360°-miljø, skal listen opdateres - se
> næste afsnit.

## 9. Sagsstatusser - `CaseStatus`-enum'et

Ligesom sagstyper er sagsstatusser tenant-specifikke. `CaseStatus` i
`src/public360_client.py` indeholder de **aktive** rækker i Næstveds
"Case status"-kodetabel (hentet live via `get_code_table_rows()`, se
afsnit 10). Medlemsnavnene er afledt af kodefeltet (`Code`), ikke af
beskrivelsen, da beskrivelsen ofte er et langt workflow-trin (fx "2.4
Under behandling - Sag afventer supplerende oplysninger fra ansøg")
frem for et kort label - se kommentaren på hvert medlem for den fulde
beskrivelse:

```python
from src.public360_client import CaseStatus

CaseStatus.R   # "recno:4"   - Reserveret sag
CaseStatus.B   # "recno:5"   - Under behandling
CaseStatus.SA  # "recno:6"   - Sag afsluttet
CaseStatus.A   # "recno:300001" - Aktiv
# ... se klassen for alle 82 medlemmer
```

To rækker deler kodenavnet `"H"` ("Høring" og "Henvist") - den anden er
derfor navngivet `CaseStatus.H_2` i stedet.

> **Vigtigt:** Dette er den *globale* "Case status"-kodetabel. Hver
> sagstype er separat konfigureret i 360° web admin med sin egen delmængde
> af tilladte statusser - en recno, der findes her, kan stadig blive
> afvist for en given `case_type` med fejlen *"The selected Case Status
> is not valid for the Case Type"*. Sker det, så tjek web admin for
> sagstypens tilladte statusser, eller prøv jer frem med en anden
> kandidat fra listen. Angives `status` slet ikke i `create_case()`,
> bruger 360° en standardstatus (recno 5 i Næstveds tenant), som heller
> ikke nødvendigvis er gyldig for enhver sagstype.

## 10. Slå kodetabeller op med `get_code_table_rows()`

Hvis `CaseType`- eller `CaseStatus`-listen bliver forældet (fx efter at
360°-administratoren har ændret konfigurationen), kan I hente den
aktuelle liste direkte fra jeres tenant:

```python
result = client.get_code_table_rows("code table: Case type", language="ENU")

for row in result["CodeTableRows"]:
    print(row["Recno"], row["Code"], row["Description"])
```

| Parameter | Beskrivelse |
|---|---|
| `code_table_name` | Navnet på kodetabellen, **inkl. præfiks**, fx `"code table: Case type"`, `"code table: Case status"`. |
| `include_expired_values` | `False` (default) viser kun aktive rækker. Sæt til `True` for også at se udløbne/inaktive koder. |
| `language` | Begræns til ét sprog, fx `"NOR"`, `"ENU"`. |
| `include_all_languages` | Returnér alle understøttede sprog samtidig. |

I stedet for at skrive koden ovenfor hver gang kan I bruge
`scripts/dump_code_table.py` til at dumpe en kodetabel fra kommandolinjen
(genbruger jeres gemte `prod`-token, se afsnit 3):

```bash
uv run python scripts/dump_code_table.py "code table: Case status"
uv run python scripts/dump_code_table.py "code table: Case type" --include-expired
```

## 11. Generelle API-kald med `get()`/`post()`

Alle andre 360°-endpoints, der ikke har en dedikeret metode endnu, kan
kaldes direkte - `get()`/`post()` håndterer automatisk Bearer-token og
retries på `401`/`429`/`5xx`:

```python
response = client.post(
    "/Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC/<Service>/<Operation>",
    json={"parameter": {...}},
)
data = response.json()
```

## 12. Scripts til automatisk drift

| Script | Formål | Kræver login? |
|---|---|---|
| `scripts/bootstrap_once.py` | Køres manuelt af et menneske, én gang | Ja |
| `scripts/robot_job.py` | Eksempel på et ubemandet, planlagt job | Nej - genbruger gemt token |
| `scripts/dump_code_table.py` | Dump en kodetabel (fx "Case status", "Case type") til konsollen, se afsnit 10 | Nej (hvis token findes) |
| `test.py` | Smoke test af bootstrap-klienterne for Næstved test/prod | Nej (hvis token findes) |

Se [AUTHENTICATE.md](AUTHENTICATE.md), afsnit 7, for hvordan menneske- og
robot-rollen hænger sammen.

## 13. Sikkerhed

- Det gemte offline token er en hemmelighed på niveau med et kodeord -
  commit det aldrig, log det aldrig, og opbevar det i jeres godkendte
  secret store.
- CPR-numre er følsomme personoplysninger - log eller gem aldrig rå
  API-svar med CPR-numre, uden det er nødvendigt og lovligt.
- Fanger I en `Public360AuthError`, er der ingen automatisk vej videre -
  en administrator skal køre `scripts/bootstrap_once.py` igen.
