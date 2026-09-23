# 360APIWrapper

Python-klient til Tietoevry Public 360° (SIF API), med authentikering via
**FK Adgangsstyring Service Accounts** og en simpel wrapper til at kalde
360°-API'et (REST/RPC) uden at skulle håndtere OAuth-flowet selv.

Kernen er `src/public360_client.py` (klassen `Public360Client`), som
håndterer:

- Login/token-håndtering (OAuth 2.0 mod Keycloak, se [AUTHENTICATE.md](AUTHENTICATE.md))
- Automatisk retry på `401`/`429`/`5xx`
- Simple `get()` / `post()` metoder til vilkårlige 360°-API-kald
- Færdige, dokumenterede metoder til udvalgte services, fx `get_cases()`

## Indhold

- [Kom i gang](#kom-i-gang)
- [Authentikering](#authentikering)
- [Søg sager med `get_cases()`](#søg-sager-med-get_cases)
- [Generelle API-kald](#generelle-api-kald)
- [Scripts](#scripts)
- [Sikkerhed](#sikkerhed)

## Kom i gang

```bash
uv sync
```

Kræver Python 3.13+ og `requests` (installeres automatisk af `uv sync`, se
`pyproject.toml`).

## Authentikering

Før klienten kan bruges, skal I have sat authentikering op via FK
Adgangsstyring. Det er beskrevet i detaljer i [AUTHENTICATE.md](AUTHENTICATE.md),
men kort fortalt skal I bruge:

**Fra Tieto (jeres 360°-kontakt):**

| Værdi | Eksempel |
|---|---|
| `realm_url` | `https://keycloak.360online.com/realms/<customer-realm>` |
| `client_id` | Bootstrap/runtime client-id oprettet til jeres integration |

**Selv besluttet:**

| Værdi | Eksempel |
|---|---|
| `tenant_host` | `kommune.public360online.com` |
| `token_storage_path` | Hvor det gemte offline token skal ligge — brug jeres secret store i produktion |

Der er intet brugernavn/kodeord at konfigurere i koden. Sæt op i to trin:

1. **Bootstrap (én gang, interaktivt)** — et menneske logger ind via FK
   Adgangsstyring i en browser og henter et langtidsholdbart offline token:

   ```python
   from src.public360_client import Public360Client

   client = Public360Client(
       realm_url="https://keycloak.360online.com/realms/<customer-realm>",
       client_id="<bootstrap-client-id>",
       tenant_host="<kommune>.public360online.com",
       token_storage_path="./fk-api-offline-token.local.json",
   )
   client.bootstrap()
   ```

   Eller kør `uv run python scripts/bootstrap_once.py`.

2. **Runtime (automatisk, ubemandet)** — alle efterfølgende kald genbruger
   det gemte token og kræver ingen login:

   ```python
   client = Public360Client(
       realm_url="https://keycloak.360online.com/realms/<customer-realm>",
       client_id="<bootstrap-client-id>",
       tenant_host="<kommune>.public360online.com",
       token_storage_path="./fk-api-offline-token.local.json",
   )
   response = client.get("/some/api/path")
   ```

Se [AUTHENTICATE.md](AUTHENTICATE.md) for det fulde flow, fejlfinding og
hvornår I skal re-bootstrappe.

## Søg sager med `get_cases()`

`Public360Client.get_cases()` er en wrapper om `CaseService/GetCases` (se
`Doc/SIF APIs - Documentation.pdf`, kapitel 7.3), til at søge sager på fx en
bestemt **sagstype** og en bestemt **borger (CPR-nummer)**.

```python
result = client.get_cases(
    cpr_number="0101001234",   # borgerens CPR-nummer
    case_type="Sak",           # sagstype (kodeværdi eller "recno:<tal>")
)

for case in result["Cases"]:
    print(case["CaseNumber"], case["Title"])

print("Antal hits:", result["TotalCount"])
```

Parametre:

| Parameter | Beskrivelse |
|---|---|
| `cpr_number` | Borgerens CPR-nummer. Sendes som `ContactReferenceNumber` og matcher sager, hvor personen er tilknyttet som kontakt. |
| `case_type` | Sagstype — enten en 360°-kodeværdi (fx `"Sak"`) eller en recno-reference (fx `"recno:2"`). Sendes som `CaseType`. |
| `max_returned_cases` | Maks. antal sager der returneres. Default `100`. |
| `page` | Sidenummer til paginering (brug altid sammen med `sort_criterion`). |
| `sort_criterion` | `"RecnoAscending"` eller `"RecnoDescending"` — brug sammen med `page` for stabil sortering. |
| `**extra_query` | Alle andre felter fra `GetCasesQuery` (fx `Recno`, `CaseNumber`, `ArchiveCode`, `LastDate`, `IncludeCaseContacts`) kan sendes med som keyword-argumenter og videresendes uændret. |

`get_cases()` kræver mindst ét søgekriterie (CPR-nummer, sagstype eller et
`extra_query`-felt) — det kaster en `ValueError`, hvis der ikke er givet
noget at søge på, jf. API'ets egen regel om, at mindst ét ikke-tomt felt
skal udfyldes.

Returværdien er det rå, parsede JSON-svar (`GetCasesResult`): en liste af
sager under `"Cases"`, samt `"TotalCount"`, `"TotalPageCount"` og
`"Successful"`.

## Generelle API-kald

Alle andre 360°-endpoints kan kaldes direkte via `get()`/`post()`, som
automatisk håndterer Bearer-token og retries:

```python
response = client.post(
    "/Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC/<Service>/<Operation>",
    json={"parameter": {...}},
)
data = response.json()
```

## Scripts

| Script | Formål |
|---|---|
| `scripts/bootstrap_once.py` | Køres manuelt af et menneske, én gang, for at hente offline token. |
| `scripts/robot_job.py` | Eksempel på et ubemandet, planlagt job der genbruger det gemte token. |
| `test.py` | Smoke test af bootstrap-klienterne for Næstved test/prod. |

Se [AUTHENTICATE.md](AUTHENTICATE.md) for hvordan de to roller (menneske vs.
robot) hænger sammen.

## Sikkerhed

- Det gemte offline token er en hemmelighed på niveau med et kodeord — commit
  det aldrig, log det aldrig, og opbevar det i jeres godkendte secret store.
- CPR-numre er følsomme personoplysninger — log eller gem aldrig rå
  API-svar, der indeholder CPR-numre, uden at det er nødvendigt og lovligt.
