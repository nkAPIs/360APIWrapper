"""
Public360Client

Encapsulates authentication and calls against the 360 API using FK
Adgangsstyring service accounts, per Tieto's guide:
"360 API Authentication via FK Adgangsstyring Service Accounts".

Requires: pip install requests
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import time
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import requests


class Public360AuthError(Exception):
    """Raised when authentication with the 360 API fails and cannot be recovered automatically."""


# TODO(sensitivity): confirm with the 360 admin / Tietoevry what the exact
# 360 meta-model field Name is for the "Følsomhed"/"Sensitivity" value that
# EventHandlerWhenCaseOrDocSensitivityIsMandatory requires on every Case (and
# Document). Confirmed on 2026-10-07 that it is NOT a standard
# CreateCaseParameter property and NOT a 360 code table - a live
# SupportService/GetCodeTableRows call against the naestved prod tenant
# returned "does not exist" for "Følsomhed", "Sensitivity" and
# "Sensitivitet". It is therefore almost certainly a custom field set via
# CreateCaseParameter.AdditionalFields (SIF docs, "7.4.7 Data Contract:
# AdditionalFieldParameter") - the field's internal meta-model Name can
# differ from its label in the 360 GUI. Update this constant once known.
SENSITIVITY_FIELD_NAME = "Sensitivity"


class CaseType(str, Enum):
    """
    Active values of the Naestved 360 tenant's "Case type" code table, for
    use as the `case_type` argument to
    Public360Client.create_case()/get_cases(). Values are "recno:<n>"
    rather than the Code string, since Code is not guaranteed unique
    (e.g. two rows are both coded "BOM Byggesag" here).

    Fetched live via client.get_code_table_rows("code table: Case type")
    against the naestved prod tenant on 2026-10-05. This list is
    tenant-specific and can change when 360 admin reconfigures the code
    table - re-run that call to refresh it if case_type lookups start
    failing.

    Note: the generic SIF-docs default, recno 2 ("Sak"/"Case"), is
    expired in this tenant and intentionally not included below.
    """

    ACCESS_REQUEST = "recno:15"  # "Access request"
    ADMINISTRATIVE_CASE = "recno:300001"  # "Administrative Case"
    EMPLOYEE_CASE = "recno:300002"  # "Employee Case"
    CITIZEN_CASE = "recno:300003"  # "Citizen Case"
    GEO_CASE = "recno:300004"  # "Geo Case"
    PPR_CASE = "recno:300005"  # "PPR Case"
    VIRKSOMHEDSSAG = "recno:300207"  # "Virksomhedssag"
    GEOSAG = "recno:500049"  # "Geosag"
    MILJOSAG = "recno:500050"  # "Miljøsag"
    NATURSAG = "recno:500051"  # "Natursag"
    ELEV = "recno:500053"  # "Elev"
    GEOSAG_KLON = "recno:500058"  # "Geosag Klon"
    BOM_BYGGESAG = "recno:500097"  # "BOM Byggesag"
    BOM_MILJOSAG = "recno:500098"  # "BOM Miljøsag"
    BOM_NATURSAG = "recno:500099"  # "BOM Natursag"
    BOM_PLANSAG = "recno:500100"  # "BOM Plansag"
    AABEN_LAND_SAG = "recno:500101"  # "Åben land sag"
    LOKALPLAN = "recno:500110"  # "Lokalplan"
    BHS_SAG = "recno:500125"  # "BHS sag"
    ADMINISTRATIVSAG = "recno:500160"  # "Administrativsag"
    BOM_BYGGESAG_500193 = "recno:500193"  # "BOM Byggesag" (second row with this code)


class AccessGroup(str, Enum):
    """
    Active, non-system-generated access groups of the Naestved 360
    tenant, for use as the `access_group` argument to
    Public360Client.create_case(). Values are "recno:<n>" rather than
    the Code string, for consistency with CaseType (and because 360
    treats AccessGroup as its own entity/lookup, not a code table).

    Fetched live via AccessGroupService/GetAccessGroups (IncludeMembers
    False, paginated) against the naestved prod tenant on 2026-10-05,
    filtered to rows with IsSystemGenerated == False. Naestved has
    ~48,900 additional system-generated access groups (e.g. one
    auto-created per case/document for row-level permissions,
    "STS_KLE_..." codes) which are intentionally excluded here - those
    are assigned automatically by 360 and are not meant to be picked by
    hand.

    This list is tenant-specific and can change when 360 admin
    reconfigures access groups - re-run the live query above to refresh
    it if access_group lookups start failing.

    Note: the generic SIF-docs example, "Public", does not exist in this
    tenant. AABEN_FOR_ALLE ("Åben for alle" / "Open to all", recno 0) is
    this tenant's closest equivalent.
    """

    AABEN_FOR_ALLE = "recno:0"  # "Åben for alle"
    ADMINISTRATORER = "recno:1"  # "Administratorer"
    ARCHIVE_ROLE = "recno:2"  # "Archive role"
    LEADERS = "recno:5"  # "Leaders"
    INDSAET_INTERNE = "recno:7"  # "Indsæt interne"
    EDIT_EXTERNAL_ENTERPRISE = "recno:9"  # "Edit external enterprise"
    EDIT_EXTERNAL_CONTACT_PERSON = "recno:10"  # "Edit external contact person"
    EDIT_EXTERNAL_PRIVATE_PERSON = "recno:11"  # "Edit external private person"
    NO_MEMBERS = "recno:14"  # "No members"
    ADMINISTRER_EKSTERNE_KONTAKTER = "recno:15"  # "Administrer eksterne kontakter"
    VIEW_SOCIAL_SECURITY_NUMBER = "recno:16"  # "View social security number"
    ALLOW_CITIZEN_INFORMATION_LOOKUP = "recno:17"  # "Allow Citizen Information Lookup"
    DELETED_CONTENT = "recno:19"  # "Deleted Content"
    MIMIRACCESS = "recno:37"  # "MimirAccess"
    PROCESS_MANAGERS = "recno:38"  # "Process Managers"
    DOKUMENTSKABELONOPRETTELSE_PERSONLIG = "recno:290001"  # "Dokumentskabelonoprettelse - personlig"
    DOKUMENTSKABELONOPRETTELSE_AFDELING = "recno:290002"  # "Dokumentskabelonoprettelse - afdeling"
    DOKUMENTSKABELONOPRETTELSE_GLOBAL = "recno:290003"  # "Dokumentskabelonoprettelse - global"
    WORKFLOW_TIL_ORIENTERING = "recno:290004"  # "Workflow til orientering"
    PROCESHAANDTERING = "recno:290006"  # "Proceshåndtering"
    DAGSORDENSSYSTEM = "recno:300002"  # "Dagsordenssystem"
    FORTROLIG = "recno:300009"  # "Fortrolig"
    LOG_VAERKTOEJ = "recno:300010"  # "Log værktøj"
    VIS_CPR_NUMMER = "recno:300011"  # "Vis cpr nummer"
    BORGERSAG = "recno:300021"  # "Borgersag"
    FUJITSU_BRUGERE = "recno:300042"  # "Fujitsu brugere"
    SLET_AKTIVE_SAGER_OG_KLADDE_DOKUMENTER = "recno:300043"  # "Slet aktive sager og kladde dokumenter"
    POSTLISTEGODKENDERE = "recno:300044"  # "Postlistegodkendere"
    SAGSSKABELONOPRETTELSE_PERSONLIG = "recno:300100"  # "Sagsskabelonoprettelse - personlig"
    SAGSSKABELONOPRETTELSE_AFDELING = "recno:300101"  # "Sagsskabelonoprettelse - afdeling"
    SAGSSKABELONOPRETTELSE_GLOBAL = "recno:300102"  # "Sagsskabelonoprettelse - global"
    SAGSOPRETTELSE_ADMINISTRATIVSAG = "recno:300103"  # "Sagsoprettelse Administrativsag"
    SAGSOPRETTELSE_PERSONALESAG = "recno:300105"  # "Sagsoprettelse Personalesag"
    SAGSOPRETTELSE_BORGERSAG = "recno:300107"  # "Sagsoprettelse Borgersag"
    SAGSOPRETTELSE_GEOSAG = "recno:300109"  # "Sagsoprettelse Geosag"
    SAGSOPRETTELSE_PPRSAG = "recno:300111"  # "Sagsoprettelse PPRsag"
    SAGSOPRETTELSE_PATIENTKLAGESAG = "recno:300113"  # "Sagsoprettelse Patientklagesag"
    SAGSOPRETTELSE_FORSIKRINGSSAG = "recno:300115"  # "Sagsoprettelse Forsikringssag"
    OPDATER_FELTER_I_GAMMEL_JOURNALPERIODE = "recno:300119"  # "Opdater felter i gammel journalperiode"
    SAGSOPRETTELSE_PERSONLIG_SAG = "recno:300120"  # "Sagsoprettelse Personlig sag"
    SAGSOPRETTELSE_VIRKSOMHEDSSAG = "recno:300122"  # "Sagsoprettelse Virksomhedssag"
    EXTERNAL_LINKS = "recno:300137"  # "External Links"
    SLET_INDSKANNEDE_DOKUMENTER = "recno:300138"  # "Slet indskannede dokumenter"
    FILSKABELONER = "recno:300139"  # "Filskabeloner"
    SHOW_ADDITIONAL_CPR_INFORMATIONS = "recno:301146"  # "Show Additional CPR Informations"
    SKAL_PAA_POSTLISTE = "recno:500500"  # "Skal på postliste"
    INFORMATIONSSIKKERHEDSUDVALGET = "recno:520164"  # "Informationssikkerhedsudvalget"
    ESDH = "recno:532015"  # "ESDH"
    SAGSSKABELONER_BFE = "recno:535072"  # "Sagsskabeloner BFE"
    HYGGE = "recno:537611"  # "Hygge"


class CaseStatus(str, Enum):
    """
    Active rows of the Naestved 360 tenant's "Case status" code table, for
    use as the `status` argument to Public360Client.create_case(). Values
    are "recno:<n>" rather than the Code string, since Code is not
    guaranteed unique (e.g. "H" appears twice here, for "Høring" and
    "Henvist"). Member names are derived from Code, not Description,
    since Description is often a long workflow step (e.g. "2.4 Under
    behandling - Sag afventer supplerende oplysninger fra ansøg") rather
    than a short label; see the trailing comment on each member for the
    full Description.

    Fetched live via client.get_code_table_rows("code table: Case status")
    against the naestved prod tenant on 2026-10-06. This list is
    tenant-specific and can change when 360 admin reconfigures the code
    table - re-run that call to refresh it if status lookups start
    failing.

    IMPORTANT: this is the *global* Case status code table. Each Case
    Type is separately configured in 360 web admin with its own subset of
    allowed statuses - a recno valid here can still be rejected for a
    given `case_type` with "The selected Case Status is not valid for the
    Case Type". If create_case() raises that error, check web admin (or
    just try another candidate below) to find a status allowed for the
    case type in use.
    """

    R = "recno:4"  # Code='R' -- Reserveret sag
    B = "recno:5"  # Code='B' -- Under behandling
    SA = "recno:6"  # Code='SA' -- Sag afsluttet
    X = "recno:7"  # Code='X' -- Sagen er ikke genstand for opfølgning
    U = "recno:8"  # Code='U' -- Sagen udgår
    KU = "recno:9"  # Code='KU' -- Kopieret uddrag
    AS = "recno:17"  # Code='AS' -- Afsluttet af sagsbehandler
    OE = "recno:19"  # Code='OE' -- Overført til eArkiv
    K = "recno:20"  # Code='K' -- Kasseret
    A = "recno:300001"  # Code='A' -- Aktiv
    S = "recno:300002"  # Code='S' -- Afsluttet
    P = "recno:300023"  # Code='P' -- Passiv
    B5_2 = "recno:300187"  # Code='B5_2' -- 5.2 – Ibrugtagningstilladelse givet
    B1_0 = "recno:500021"  # Code='B1_0' -- 1.0 Screening - Sag modtaget, afventer screening
    B1_1 = "recno:500022"  # Code='B1_1' -- 1.1 Screening - Mangelbrev sendt.
    B1_2 = "recno:500023"  # Code='B1_2' -- 1.2 Screening - Suppl. oplysninger modtaget
    B1_3 = "recno:500024"  # Code='B1_3' -- 1.3 Screening - Screening afsluttet, klar til behandling
    B2_0 = "recno:500027"  # Code='B2_0' -- 2.0 Sagsbehandling - Igangværende
    B2_1 = "recno:500028"  # Code='B2_1' -- 2.1 Sagsbehandling - Mangler supplerende oplysninger fra ansøger
    B2_3 = "recno:500030"  # Code='B2_3' -- 2.3 Sagsbehandling - Høring
    B2_4 = "recno:500031"  # Code='B2_4' -- 2.4 Sagsbehandling - Behandles i anden afdeling
    B3_0 = "recno:500037"  # Code='B3_0' -- 3.0 Afgjort - Meddelt byggetilladelse
    B3_1 = "recno:500038"  # Code='B3_1' -- 3.1 Afgjort - Kræver ikke tilladelse
    B3_2 = "recno:500039"  # Code='B3_2' -- 3.2 Afgjort - Meddelt afslag
    B4_0 = "recno:500040"  # Code='B4_0' -- 4.0 Påbegyndt - Mangler dokumentation
    B4_1 = "recno:500041"  # Code='B4_1' -- 4.1 Påbegyndt - Påbegyndelse modtaget
    B5_0 = "recno:500042"  # Code='B5_0' -- 5.0 Færdigmeldt - Mangler dokumentation
    B5_1 = "recno:500043"  # Code='B5_1' -- 5.1 Færdigmeldt - Færdigmelding modtaget
    B6_0 = "recno:500044"  # Code='B6_0' -- 6.0 Sag afsluttet
    B7_0 = "recno:500045"  # Code='B7_0' -- 7.0 Sag annulleret
    MN1_0 = "recno:500049"  # Code='MN1_0' -- 1.0 Screening - Ansøgningen er modtaget
    MN1_1 = "recno:500050"  # Code='MN1_1' -- 1.1 Screening - Venter på yderligere oplysninger/materiale
    MN1_2 = "recno:500051"  # Code='MN1_2' -- 1.2 Screening - Suppl. oplysninger modtaget
    MN1_3 = "recno:500052"  # Code='MN1_3' -- 1.3 Screening - Fuld oplyst med fyldestgørende materiale
    MN2_0 = "recno:500053"  # Code='MN2_0' -- 2.0 Under behandling - Igangværende
    MN2_1 = "recno:500055"  # Code='MN2_1' -- 2.1 Under behandling - Sagen er i høring
    MN2_2 = "recno:500056"  # Code='MN2_2' -- 2.2 Under behandling - Høring afsluttet
    MN2_3 = "recno:500057"  # Code='MN2_3' -- 2.3 Under behandling - Sagen er under politisk behandling
    MN2_4 = "recno:500058"  # Code='MN2_4' -- 2.4 Under behandling - Sag afventer supplerende oplysninger fra ansøg
    MN2_5 = "recno:500059"  # Code='MN2_5' -- 2.5 Under behandling - Suppl. oplysninger modtaget
    MN2_6 = "recno:500061"  # Code='MN2_6' -- 2.6 Under behandling - Sagen behandles af anden myndighed
    MN2_7 = "recno:500062"  # Code='MN2_7' -- 2.7 Under behandling - Afgørelse modtaget fra anden myndighed
    MN3_0 = "recno:500063"  # Code='MN3_0' -- 3.0 Afgørelse - Meddelt tilladelse
    MN3_1 = "recno:500064"  # Code='MN3_1' -- 3.1 Afgørelse - Meddelt afslag
    MN5_0 = "recno:500065"  # Code='MN5_0' -- 5.0 Færdigmelding mangler
    MN5_1 = "recno:500066"  # Code='MN5_1' -- 5.1 Arbejdet er færdigmeldt
    MN6_0 = "recno:500067"  # Code='MN6_0' -- 6.0 Sagen er afsluttet
    MN7_0 = "recno:500068"  # Code='MN7_0' -- 7.0 Sagen er afslået
    MN8_0 = "recno:500069"  # Code='MN8_0' -- 8.0 Sagen er annulleret
    M = "recno:500094"  # Code='M' -- Modtaget
    I = "recno:500095"  # Code='I' -- Igangværende
    S_1P = "recno:500096"  # Code='1P' -- 1. Politiske behandling (Igangsættelse)
    UF = "recno:500097"  # Code='UF' -- Udarbejdelse af forslag
    IH = "recno:500098"  # Code='IH' -- Intern høring
    S_2P = "recno:500099"  # Code='2P' -- 2. Politiske behandling (Forslag)
    H = "recno:500100"  # Code='H' -- Høring
    OH = "recno:500101"  # Code='OH' -- Opsamling på høring
    S_3P = "recno:500102"  # Code='3P' -- 3. Politiske behandling (Vedtagelse)
    OF = "recno:500103"  # Code='OF' -- Offentliggørelse
    MA = "recno:500104"  # Code='MA' -- Modtaget/afventer sagsbehandling
    AAS = "recno:500105"  # Code='AAS' -- Afventer ansøger
    AI = "recno:500106"  # Code='AI' -- Afventer internt
    AF = "recno:500107"  # Code='AF' -- Afgjort
    VP = "recno:500108"  # Code='VP' -- Varsel om påbud
    PB = "recno:500109"  # Code='PB' -- Påbud
    PK = "recno:500110"  # Code='PK' -- Påklaget
    HE = "recno:500111"  # Code='HE' -- Henlagt
    TM = "recno:500112"  # Code='TM' -- Til udvalgsmøde
    AAM = "recno:500113"  # Code='AAM' -- Afventer anden myndighed
    GROEN = "recno:500114"  # Code='GRØN' -- Grøn
    GUL = "recno:500115"  # Code='GUL' -- Gul
    ROED = "recno:500116"  # Code='RØD' -- Rød
    N4_0 = "recno:500121"  # Code='N4_0' -- 4.0 Tilladelse/godkendelse udstedt
    AFV = "recno:500146"  # Code='AFV' -- Afventer
    H_2 = "recno:500147"  # Code='H' -- Henvist
    SM = "recno:500160"  # Code='SM' -- Servicemål
    PA = "recno:500166"  # Code='PA' -- Politianmeldelse
    SMAS = "recno:500175"  # Code='SMAS' -- Sag modtaget - afventer screening
    MS = "recno:500176"  # Code='MS' -- Mangelrev sendt
    SOM = "recno:500177"  # Code='SOM' -- Supplerende oplysninger modtaget
    AFA = "recno:500178"  # Code='AFA' -- Afgjort - Afslag
    AFVE = "recno:500179"  # Code='AFVE' -- Afventer


class DocumentCategory(str, Enum):
    """
    Active rows of the Naestved 360 tenant's "Document category" code
    table, for use as the `category` argument to
    Public360Client.create_document(). Values are "recno:<n>". Member
    names are derived from Code, with Danish letters transliterated
    (å=AA, ø=OE, æ=AE).

    Fetched via Public360Client.get_document_categories() on 2026-10-27.
    This list is tenant-specific and can change when 360 admin
    reconfigures the code table - re-run that call to refresh it.
    """

    INDGAAENDE = "recno:110"  # Code='Indgående'
    UDGAAENDE = "recno:111"  # Code='Udgående'
    HAANDBOG = "recno:120"  # Code='Håndbog'
    INSTRUKS = "recno:121"  # Code='Instruks'
    PROCEDURE = "recno:122"  # Code='Procedure'
    SKEMA = "recno:123"  # Code='Skema'
    PLAN = "recno:124"  # Code='Plan'
    KONTRAKT = "recno:125"  # Code='Kontrakt'
    SVAR_PAA_AKTINDSIGT = "recno:127"  # Code='Svar på aktindsigt'
    RUTINE = "recno:305"  # Code='Rutine'
    ANMODNING_OM_AKTINDSIGT_I = "recno:311"  # Code='Anmodning om aktindsigt i'
    HISTORISK_DOKUMENT_FRA_EARKIV = "recno:314"  # Code='Historisk dokument fra eArkiv'
    OVERSIGT_SAGSNOTER = "recno:342"  # Code='Oversigt sagsnoter'
    AKTINDSIGTSRAPPORT = "recno:379"  # Code='Aktindsigtsrapport'
    AKTINDSIGTSKOPI = "recno:380"  # Code='Aktindsigtskopi'
    HOERING_OG_OFFENTLIG_INSPEKTION = "recno:391"  # Code='Høring og offentlig inspektion'
    YDERLIGERE_INFORMATION_MINDRE_MANGEL = "recno:433"  # Code='Yderligere information - Mindre mangel'
    YDERLIGERE_INFORMATION_VAESENTLIG_MANGEL = "recno:434"  # Code='Yderligere information - Væsentlig mangel'
    HOERINGSSVAR = "recno:435"  # Code='Høringssvar'
    KOMMENTAR = "recno:436"  # Code='Kommentar'
    MANGELBREV_MINDRE_MANGEL = "recno:437"  # Code='Mangelbrev - Mindre mangel'
    MANGELBREV_VAESENTLIG_MANGEL = "recno:438"  # Code='Mangelbrev - Væsentlig mangel'
    BEKENDTGOERELSE = "recno:439"  # Code='Bekendtgørelse'
    INTERNT = "recno:60005"  # Code='Internt'
    BESLUTNINGSDOKUMENT = "recno:60006"  # Code='Beslutningsdokument' -- Beslutning (MU)
    PERSONALEHAANDBOG = "recno:95509"  # Code='Personalehåndbog'
    INDKOMMENDE_DOKUMENT_UDEN_OPFOELGNING = "recno:95564"  # Code='Indkommende dokument (uden opfølgning)'
    BESLUTNINGSBREV = "recno:99002"  # Code='Beslutningsbrev'
    ANSOEGNING = "recno:99012"  # Code='Ansøgning'
    INDSIGELSE = "recno:99050"  # Code='Indsigelse'
    AKTINDSIGTSDOKUMENT = "recno:300054"  # Code='Aktindsigtsdokument'
    JOURNALNOTE = "recno:300087"  # Code='Journalnote'
    MEMO_AFSENDELSE = "recno:320011"  # Code='MeMo-afsendelse'


class DocumentStatus(str, Enum):
    """
    Active rows of the Naestved 360 tenant's "Journal status" code table
    (a document's Status field), for use as the `status` argument to
    Public360Client.create_document(). Values are "recno:<n>". Member
    names are derived from Code; the trailing comment is the Description.

    Fetched via Public360Client.get_document_statuses() on 2026-10-27.
    This list is tenant-specific and can change when 360 admin
    reconfigures the code table - re-run that call to refresh it.
    """

    K = "recno:1"  # Code='K' -- Kladde
    M = "recno:2"  # Code='M' -- Midlertidig journalført af arkivet
    R = "recno:3"  # Code='R' -- Registreret i første hånd eller ajourført af sagsbehandler/leder
    F = "recno:4"  # Code='F' -- Færdig fra sagsbehandler/leder og klargjort for afsendelse
    V = "recno:5"  # Code='V' -- Videresendt
    E = "recno:6"  # Code='E' -- Endelig
    A = "recno:7"  # Code='A' -- Registrering afsluttet, arkiveksemplar tilgængelig
    D = "recno:8"  # Code='D' -- Slettet
    S = "recno:9"  # Code='S' -- Sendt til godkendelse
    G = "recno:10"  # Code='G' -- Godkendt
    I = "recno:11"  # Code='I' -- Ikke godkendt
    T = "recno:12"  # Code='T' -- Til kommentering
    SIGNERET = "recno:14"  # Code='Signeret' -- Signeret
    KA = "recno:16"  # Code='KA' -- Kasseret
    KK = "recno:17"  # Code='KK' -- Klar til kassation
    US = "recno:18"  # Code='US' -- Under signering


class Public360Client:
    """
    Authentication happens in two phases:

    Phase 1 - Bootstrap (one-time, interactive):
        OAuth 2.0 Device Authorization Grant with PKCE. A human operator
        opens a verification URL in a browser and logs in via FK
        Adgangsstyring (SAML, delegated by Keycloak). The result is an
        "offline token" (a refresh token with the offline_access scope),
        which does not expire until it is revoked or the associated
        FK service-user access is removed.

    Phase 2 - Runtime (ongoing, unattended):
        OAuth 2.0 Refresh Token Grant. The stored offline token is
        exchanged for a short-lived access token (~10 min), which is
        sent as a Bearer token on every API call. Keycloak may rotate
        the offline token on each exchange; the rotated value is
        persisted automatically.

    Required login info / inputs
    -----------------------------
    From Tieto (your 360 representative), requested once per integration:
        - realm_url:
              e.g. "https://keycloak.360online.com/realms/<customer-realm>"
        - client_id:
              the bootstrap/runtime client id Tieto created for this
              integration (one client per integration is recommended)

    Decided locally by you (the customer):
        - tenant_host:
              your 360 tenant hostname, e.g. "customer.public360online.com"
        - token_storage_path:
              where the offline token is persisted. Treat this file as a
              secret equivalent to a password: never commit it, never log
              its contents, never send it to the API, and store it in your
              organization's approved secret storage (e.g. a secrets
              manager) instead of a plain local file where possible.
    -- base_endpoint:
              the base path for all 360 API calls. Defaults to
              "/Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC",
              which is the standard for 360 v2 API calls. Override only
              if your tenant has a custom endpoint path configured in 360 web admin.
              
    There is no username/password to hardcode anywhere. The one human
    login happens interactively in a browser during bootstrap(); every
    subsequent run only needs the stored offline token.
    """

    OFFLINE_SCOPE = "openid offline_access"

    def __init__(
        self,
        realm_url: str,
        client_id: str,
        tenant_host: str,
        base_endpoint: str = "/Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC",
        token_storage_path: str = "./fk-api-offline-token.local.json",
        token:str = None,
        timeout: float = 30.0,
    ):
        self.realm_url = realm_url.rstrip("/")
        self.client_id = client_id
        self.api_base_url = f"https://{tenant_host}"
        self.token_storage_path = token_storage_path
        self.timeout = timeout
        self.base_endpoint = base_endpoint.rstrip("/")
        self.token = token
        self._session = requests.Session()
        self._endpoints: Optional[dict] = None
        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def _discover(self) -> dict:
        """Fetch and cache the realm's OpenID well-known configuration."""
        if self._endpoints is None:
            resp = self._session.get(
                f"{self.realm_url}/.well-known/openid-configuration",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            self._endpoints = resp.json()
        return self._endpoints

    # ------------------------------------------------------------------
    # Phase 1: Bootstrap (one-time)
    # ------------------------------------------------------------------
    def bootstrap(self, open_browser: bool = True) -> None:
        """
        Run the OAuth 2.0 Device Authorization Grant with PKCE once, to
        obtain and store an offline token. Requires a human to
        authenticate via FK Adgangsstyring in a browser. Safe to re-run
        (overwrites any previously stored token).
        """
        endpoints = self._discover()
        code_verifier, code_challenge = self._generate_pkce_pair()

        device_resp = self._session.post(
            endpoints["device_authorization_endpoint"],
            data={
                "client_id": self.client_id,
                "scope": self.OFFLINE_SCOPE,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
            timeout=self.timeout,
        )
        device_resp.raise_for_status()
        device = device_resp.json()

        verification_uri = device.get("verification_uri_complete") or device["verification_uri"]
        print(f"To authenticate, open this URL and log in via FK Adgangsstyring:\n  {verification_uri}")
        if open_browser:
            webbrowser.open(verification_uri)

        token = self._poll_for_token(
            token_endpoint=endpoints["token_endpoint"],
            device_code=device["device_code"],
            code_verifier=code_verifier,
            interval=device.get("interval", 5),
            expires_in=device.get("expires_in", 600),
        )

        self._store_offline_token(token)
        print(f"Bootstrap complete. Offline token stored at {self.token_storage_path}")

    @staticmethod
    def _generate_pkce_pair() -> tuple[str, str]:
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def _poll_for_token(
        self,
        token_endpoint: str,
        device_code: str,
        code_verifier: str,
        interval: int,
        expires_in: int,
    ) -> dict:
        deadline = time.time() + expires_in
        while time.time() < deadline:
            time.sleep(interval)
            resp = self._session.post(
                token_endpoint,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": self.client_id,
                    "code_verifier": code_verifier,
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json()

            error = resp.json().get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            raise Public360AuthError(f"Device authorization failed: {error}")

        raise Public360AuthError("Device authorization timed out before the user completed login.")

    # ------------------------------------------------------------------
    # Token storage
    # ------------------------------------------------------------------
    def _store_offline_token(self, token: dict) -> None:
        doc = {"refresh_token": token["refresh_token"]}
        with open(self.token_storage_path, "w") as f:
            json.dump(doc, f)
        os.chmod(self.token_storage_path, stat.S_IRUSR | stat.S_IWUSR)

    def _load_offline_token(self) -> str:
        if not os.path.exists(self.token_storage_path):
            raise Public360AuthError(
                "No offline token found. Run bootstrap() once (interactively) "
                "before using the client at runtime."
            )
        with open(self.token_storage_path) as f:
            doc = json.load(f)
        return doc["refresh_token"]

    # ------------------------------------------------------------------
    # Phase 2: Runtime
    # ------------------------------------------------------------------
    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires_at:
            return self._access_token

        endpoints = self._discover()
        offline_token = self.token if self.token else self._load_offline_token()

        resp = self._session.post(
            endpoints["token_endpoint"],
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": offline_token,
            },
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            body = resp.json() if resp.content else {}
            if body.get("error") == "invalid_grant":
                raise Public360AuthError(
                    "Offline token is revoked or expired. Re-run bootstrap() to obtain a new one."
                )
            resp.raise_for_status()

        token = resp.json()

        new_refresh_token = token.get("refresh_token")
        if new_refresh_token and new_refresh_token != offline_token:
            self._store_offline_token(token)

        self._access_token = token["access_token"]
        self._access_token_expires_at = time.time() + token.get("expires_in", 300) - 30
        return self._access_token

    def revoke(self) -> None:
        """Immediately invalidate the stored offline token at Keycloak."""
        offline_token = self.token if self.token else self._load_offline_token()
        resp = self._session.post(
            f"{self.realm_url}/protocol/openid-connect/revoke",
            data={
                "token": offline_token,
                "client_id": self.client_id,
                "token_type_hint": "refresh_token",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------
    def call_api(
        self,
        method: str,
        path: str,
        headers: Optional[dict] = None,
        **kwargs,
    ) -> requests.Response:
        """
        Call the 360 API at `path` (relative to the tenant host unless it
        is already a full URL), attaching a fresh Bearer access token.

        Applies the retry/error baseline from the integration guide:
        retry once on 401 (with a forced token refresh), honor
        Retry-After on 429, and back off exponentially on 5xx.
        """
        url = path if path.startswith("http") else f"{self.api_base_url}{path}"
        headers = dict(headers or {})
        max_retries = 5

        for attempt in range(max_retries + 1):
            headers["Authorization"] = f"Bearer {self._get_access_token()}"
            resp = self._session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

            if resp.status_code == 401 and attempt == 0:
                self._access_token = None
                continue
            if resp.status_code == 429 and attempt < max_retries:
                time.sleep(float(resp.headers.get("Retry-After", 2 ** attempt)))
                continue
            if resp.status_code >= 500 and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue

            resp.raise_for_status()
            return resp

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.call_api("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.call_api("POST", path, **kwargs)

    # ------------------------------------------------------------------
    # SupportService
    # ------------------------------------------------------------------
    def get_code_table_rows(
        self,
        code_table_name: str,
        include_expired_values: bool = False,
        language: Optional[str] = None,
        include_all_languages: bool = False,
    ) -> dict:
        """
        Fetch the rows of a 360 code table via SupportService/GetCodeTableRows.

        Args:
            code_table_name: Name of the code table, e.g. "Case type",
                "Case status", "Document category".
            include_expired_values: If False (default), only valid/active
                rows are returned.
            language: Restrict rows to one language, e.g. "NOR", "ENU".
            include_all_languages: Return rows for every supported
                language in 360. Default False.

        Returns:
            The parsed JSON GetCodeTableRowsResult, e.g.
            {"CodeTableRows": [...], "Successful": ..., ...}.
        """
        query: dict = {
            "CodeTableName": code_table_name,
            "IncludeExpiredValues": include_expired_values,
            "IncludeAllLangauges": include_all_languages,
        }
        if language:
            query["Language"] = language

        response = self.post(
            f"{self.base_endpoint}/SupportService/GetCodeTableRows",
            json={"parameter": query},
        )
        return response.json()

    def get_document_categories(
        self, include_expired_values: bool = False
    ) -> list[dict]:
        """
        Rows of the "Document category" code table, for create_document's
        `category` argument. Use "recno:<Recno>" as the value.
        """
        result = self.get_code_table_rows(
            "code table: Document category",
            include_expired_values=include_expired_values,
        )
        return result.get("CodeTableRows", [])

    def get_document_statuses(
        self, include_expired_values: bool = False
    ) -> list[dict]:
        """
        Rows of the "Journal status" code table (a document's Status
        field), for create_document's `status` argument. Use
        "recno:<Recno>" as the value.
        """
        result = self.get_code_table_rows(
            "code table: Journal status",
            include_expired_values=include_expired_values,
        )
        return result.get("CodeTableRows", [])

    def ping(self, service: str = "CaseService") -> None:
        """
        Call Ping() on the given service endpoint to confirm connectivity:
        that the access token is valid, the service is reachable and
        correctly installed, and your user has at least read access to
        360. Raises on failure; returns None on success.
        """
        return self.post(f"{self.base_endpoint}/{service}/Ping", json={"parameter": {}})

    # ------------------------------------------------------------------
    # CaseService
    # ------------------------------------------------------------------
    def get_cases(
        self,
        cpr_number: Optional[str] = None,
        case_type: Optional[Union[str, CaseType]] = None,
        external_id: Optional[str] = None,
        external_id_type: Optional[str] = None,
        max_returned_cases: int = 100,
        page: Optional[int] = None,
        sort_criterion: Optional[str] = None,
        **extra_query,
    ) -> dict:
        """
        Search for cases via CaseService/GetCases.

        Args:
            cpr_number: The citizen's CPR number (personal id number). Maps
                to the GetCasesQuery "ContactReferenceNumber" field, which
                searches case-contact relations for a private person (or an
                enterprise, via CVR/EnterpriseNumber) with this value.
            case_type: The case type to filter by. Either a 360 code value
                (e.g. "Sak") or a recno reference (e.g. "recno:2"). Maps to
                the GetCasesQuery "CaseType" field.
            external_id: ID of this case in another (non-360) system, as
                previously set via create_case()'s external_id. Maps to
                the GetCasesQuery "ExternalId" field (an
                ExternalIdParameter {"Id": ..., "Type": ...}). Must be
                given together with external_id_type.
            external_id_type: Name of the other system that external_id
                belongs to (e.g. "Visma"). Maps to ExternalIdParameter's
                "Type".
            max_returned_cases: Max number of cases to return. Default 100.
            page: Pagination page number. Use together with
                sort_criterion for a stable result order across pages.
            sort_criterion: "RecnoAscending" or "RecnoDescending". Should
                be set whenever `page` is used.
            **extra_query: Any other GetCasesQuery field to pass through
                as-is (e.g. Recno, CaseNumber, ArchiveCode, LastDate,
                IncludeCaseContacts). See the SIF API documentation,
                chapter "7.3 GetCases", for the full list of fields.

        Returns:
            The parsed JSON GetCasesResult, e.g. {"Cases": [...],
            "TotalCount": ..., "Successful": ..., ...}.

        Raises:
            ValueError: if no search criterion was supplied at all
                (GetCases requires at least one), or if only one of
                external_id/external_id_type was given.
        """
        if bool(external_id) != bool(external_id_type):
            raise ValueError(
                "get_cases requires both external_id and external_id_type "
                "together, not just one of them."
            )
        if not cpr_number and not case_type and not external_id and not extra_query:
            raise ValueError(
                "get_cases requires at least one search criterion "
                "(cpr_number, case_type, external_id, or another "
                "GetCasesQuery field passed via extra_query)."
            )

        query: dict = {"MaxReturnedCases": max_returned_cases}
        if cpr_number:
            query["ContactReferenceNumber"] = cpr_number
        if case_type:
            query["CaseType"] = case_type
        if external_id:
            query["ExternalId"] = {"Id": external_id, "Type": external_id_type}
        if page is not None:
            query["Page"] = page
        if sort_criterion:
            query["SortCriterion"] = sort_criterion
        query.update(extra_query)

        response = self.post(
            f"{self.base_endpoint}/CaseService/GetCases",
            json={"parameter": query},
        )
        return response.json()

#     def create_case(
#         self,
#         title: str,
#         case_type: Union[str, CaseType]=None,
#         sensitivity: str=None,
#         unofficial_title: Optional[str] = None,
#         status: Optional[Union[str, CaseStatus]] = None,
#         access_code: Optional[str] = None,
#         access_group: Optional[Union[str, AccessGroup]] = None,
#         journal_unit: Optional[str] = None,
#         sub_archive: Optional[str] = None,
#         external_id: Optional[str] = None,
#         external_id_type: Optional[str] = None,
#         responsible_person_id_number: Optional[str] = None,
#         responsible_person_recno: Optional[str] = None,
#         responsible_person_email: Optional[str] = None,
#         responsible_person_user_id: Optional[str] = None,
#         **extra_fields,
#     ) -> dict:
#         """
#         Create a case (CaseType "Sak"/Noark Sak) via CaseService/CreateCase.

#         `case_type` and `sensitivity` are mandatory here (even though SIF
#         itself treats both as optional) because, in the Naestved tenant,
#         omitting either one is guaranteed to make 360 reject the insert:
#         the generic default case_type (recno 2) is expired in this tenant,
#         and the eDoc event handler
#         EventHandlerWhenCaseOrDocSensitivityIsMandatory rejects any Case
#         (or Document) insert that doesn't carry a sensitivity value, with
#         "Der er ikke angivet noget følsomhed" ("no sensitivity specified").

#         Args:
#             title: Case description. Maps to the CreateCaseParameter
#                 "Title" field. Mandatory.
#             case_type: Code value, recno, or a CaseType member (e.g.
#                 CaseType.ADMINISTRATIVE_CASE). Maps to "CaseType".
#             sensitivity: The case's "Følsomhed"/sensitivity classification,
#                 required by this tenant's EventHandlerWhenCaseOrDocSensitivityIsMandatory
#                 rule. Sent as an AdditionalFieldParameter named
#                 SENSITIVITY_FIELD_NAME. NOT yet backed by a `Sensitivity`
#                 enum: unlike CaseType/CaseStatus/AccessGroup, this is not a
#                 360 code table (confirmed empirically - see
#                 SENSITIVITY_FIELD_NAME's comment) and its valid values
#                 and exact field Name still need confirming with the 360
#                 admin / Tietoevry. Pass the raw string value for now;
#                 swap in an enum here once confirmed.
#             unofficial_title: Maps to "UnofficialTitle". Defaults to
#                 `title` in 360 if not set.
#             status: Code value, recno, or a CaseStatus member (e.g.
#                 CaseStatus.B for "Under behandling"). Maps to "Status".
#                 Not every status is valid for every case_type - 360 will
#                 reject the combination with "The selected Case Status is
#                 not valid for the Case Type" if so; check 360 web admin
#                 for the case type's allowed statuses. Closing statuses
#                 require ArchiveCodes to also be set (pass via
#                 extra_fields).
#             access_code: Code value or recno. Maps to "AccessCode". Some
#                 access codes require "Paragraph" to also be set (pass via
#                 extra_fields).
#             access_group: Code value, recno, or an AccessGroup member.
#                 Maps to "AccessGroup".
#             journal_unit: Code value or recno. Maps to "JournalUnit".
#             sub_archive: Code value or recno. Maps to "SubArchive".
#             external_id: ID of this case in another (non-360) system,
#                 for later lookup via get_cases(external_id=...). Maps to
#                 "ExternalId" (an ExternalIdParameter {"Id": ...,
#                 "Type": ...}). Must be given together with
#                 external_id_type.
#             external_id_type: Name of the other system that external_id
#                 belongs to (e.g. "Visma"). Maps to ExternalIdParameter's
#                 "Type".
#             responsible_person_id_number: External ID of the responsible
#                 person. Maps to "ResponsiblePersonIdNumber". Provide only
#                 one of the four responsible_person_* arguments.
#             responsible_person_recno: Recno of the responsible person.
#                 Maps to "ResponsiblePersonRecno".
#             responsible_person_email: Email of the responsible person.
#                 Maps to "ResponsiblePersonEmail".
#             responsible_person_user_id: Username of the responsible person
#                 (e.g. "no\\name.name"). Maps to "ResponsiblePersonUserId".
#             **extra_fields: Any other CreateCaseParameter field to pass
#                 through as-is (e.g. ArchiveCodes, Contacts, Keywords,
#                 Category, Project, Remarks). See the SIF API
#                 documentation, chapter "7.1 CreateCase", for the full
#                 list of fields. Pass "AdditionalFields" here (a list of
#                 {"Name": ..., "Value": ...} dicts) for any other custom
#                 field besides sensitivity - it will be merged with the
#                 sensitivity entry, not overwritten.

#         Returns:
#             The parsed JSON CaseOperationResult, e.g. {"Recno": ...,
#             "CaseNumber": ..., "UID": ..., ...}.

#         Raises:
#             ValueError: if `title` or `sensitivity` is empty, or if only
#                 one of external_id/external_id_type was given.
#         """
#         if not title:
#             raise ValueError("create_case requires a non-empty title.")
#         # if not sensitivity:
#         #     raise ValueError("create_case requires a non-empty sensitivity.")
#         if bool(external_id) != bool(external_id_type):
#             raise ValueError(
#                 "create_case requires both external_id and "
#                 "external_id_type together, not just one of them."
#             )

#         additional_fields = list(extra_fields.pop("AdditionalFields", []))
# #        additional_fields.append({"Name": SENSITIVITY_FIELD_NAME, "Value": sensitivity})

#         parameter: dict = {
#             "Title": title,
#             #"CaseType": case_type,
#             "AdditionalFields": additional_fields,
#         }
#         if unofficial_title:
#             parameter["UnofficialTitle"] = unofficial_title
#         if status:
#             parameter["Status"] = status
#         if access_code:
#             parameter["AccessCode"] = access_code
#         if access_group:
#             parameter["AccessGroup"] = access_group
#         if journal_unit:
#             parameter["JournalUnit"] = journal_unit
#         if sub_archive:
#             parameter["SubArchive"] = sub_archive
#         if external_id:
#             parameter["ExternalId"] = {"Id": external_id, "Type": external_id_type}
#         if responsible_person_id_number:
#             parameter["ResponsiblePersonIdNumber"] = responsible_person_id_number
#         if responsible_person_recno:
#             parameter["ResponsiblePersonRecno"] = responsible_person_recno
#         if responsible_person_email:
#             parameter["ResponsiblePersonEmail"] = responsible_person_email
#         if responsible_person_user_id:
#             parameter["ResponsiblePersonUserId"] = responsible_person_user_id
#         parameter.update(extra_fields)

#         response = self.post(
#             f"{self.base_endpoint}/CaseService/CreateCase",
#             json={"parameter": parameter},
#         )
#         return response.json()

    # ------------------------------------------------------------------
    # UserService
    # ------------------------------------------------------------------
    def get_users(
        self,
        user_id: Optional[str] = None,
        contact_external_id: Optional[str] = None,
        contact_recno: Optional[str] = None,
        page: Optional[int] = None,
        max_rows: Optional[int] = None,
        sort_criterion: Optional[str] = None,
        **extra_query,
    ) -> dict:
        """
        Search for users via UserService/GetUsers.

        Args:
            user_id: The ID that identifies the User (typically
                "domain\\user"). Maps to the GetUsersParameters "UserId"
                field.
            contact_external_id: Search users associated with this
                contact's external id. Maps to "ContactExternalId".
            contact_recno: Search users associated with this contact's
                recno (e.g. "recno:123"). Maps to "ContactRecno".
            page: Pagination page number, 0-indexed. Defaults to 0.
                Only applies when none of user_id/contact_external_id/
                contact_recno is given. Should be used together with
                sort_criterion for a stable result order across pages.
            max_rows: Max number of users to return per page. Defaults
                to all. Only applies when none of user_id/
                contact_external_id/contact_recno is given.
            sort_criterion: "RecnoAscending" or "RecnoDescending",
                applied before page/max_rows. Should be set whenever
                `page` is used.
            **extra_query: Any other GetUsersParameters field to pass
                through as-is. See the SIF API documentation, chapter
                "5.2 GetUsers", for the full list of fields.

        Returns:
            The parsed JSON GetUsersResult, e.g. {"Users": [...],
            "TotalCount": ..., "TotalPageCount": ..., "Successful": ...}.
            Each entry in "Users" is a UserBase object (Login,
            ContactExternalId, ContactRecno, IsActive, Profiles,
            AccessGroups, IsServiceUser, Language).
        """
        query: dict = {}
        if user_id:
            query["UserId"] = user_id
        if contact_external_id:
            query["ContactExternalId"] = contact_external_id
        if contact_recno:
            query["ContactRecno"] = contact_recno
        if page is not None:
            query["Page"] = page
        if max_rows is not None:
            query["MaxRows"] = max_rows
        if sort_criterion:
            query["SortCriterion"] = sort_criterion
        query.update(extra_query)

        response = self.post(
            f"{self.base_endpoint}/UserService/GetUsers",
            json={"parameter": query},
        )
        return response.json()

    def find_users_by_email(self, email: str, include_alternative: bool = True) -> dict:
        """
        Find users by their contact person's email address.

        UserService/GetUsers has no Email criterion - only UserId,
        ContactExternalId or ContactRecno. This looks the contact person
        up first via ContactService/GetContactPersons (which does support
        Email/AlternativeEmail), then resolves each matching contact to
        its user(s) via get_users(contact_recno=...).

        Args:
            email: Email address to search for.
            include_alternative: Also match contacts whose
                AlternativeEmail equals `email`, not just Email. Default
                True.

        Returns:
            A list of GetUsersResult["Users"] entries (UserBase objects,
            see get_users()) across all contacts that matched the email.
            Empty list if no contact or no user was found.
        """
        contacts = self.get_contact_persons(email=email)["ContactPersons"]
        if include_alternative:
            contacts += self.get_contact_persons(alternative_email=email)["ContactPersons"]

        users = []
        seen_recnos = set()
        for contact in contacts:
            recno = contact["Recno"]
            if recno in seen_recnos:
                continue
            seen_recnos.add(recno)
            result = self.get_users(contact_recno=f"recno:{recno}")
            users.extend(result["Users"])
        return users

    def find_person_recno(self, name_or_email: str) -> int:
        """
        Find the recno of a contact person, for use as responsible_recno
        (ResponsiblePersonRecno).

        If `name_or_email` contains "@" it is matched exactly against
        Email (then AlternativeEmail). Otherwise it is a partial name
        search limited to active contacts.

        Raises ValueError if no contact matches, or if more than one does
        (the message lists the candidates so you can refine the search).
        """
        if "@" in name_or_email:
            contacts = self.get_contact_persons(email=name_or_email)["ContactPersons"]
            if not contacts:
                contacts = self.get_contact_persons(
                    alternative_email=name_or_email
                )["ContactPersons"]
        else:
            contacts = self.get_contact_persons(
                name=name_or_email, active=True
            )["ContactPersons"]

        if not contacts:
            raise ValueError(f"No contact person found for {name_or_email!r}")
        if len(contacts) > 1:
            found = ", ".join(f"{c['Recno']} ({c.get('Name')})" for c in contacts)
            raise ValueError(
                f"{len(contacts)} contacts match {name_or_email!r}: {found}"
            )
        return contacts[0]["Recno"]

    # ------------------------------------------------------------------
    # ContactService
    # ------------------------------------------------------------------
    def get_contact_persons(
        self,
        name: Optional[str] = None,
        recno: Optional[str] = None,
        external_id: Optional[str] = None,
        email: Optional[str] = None,
        alternative_email: Optional[str] = None,
        active: Optional[bool] = None,
        categories: Optional[list] = None,
        page: Optional[int] = None,
        max_rows: Optional[int] = None,
        sort_criterion: Optional[str] = None,
        **extra_query,
    ) -> dict:
        """
        Search for contact persons via ContactService/GetContactPersons.

        Args:
            name: Partial name search. Maps to "Name" (360° field
                Contact-SearchName) - returns all contacts whose name
                contains this value.
            recno: Recno (unique id in 360) of the contact. Must be an
                exact match. Maps to "Recno".
            external_id: External identity number of the contact. Must
                be an exact match. Maps to "ExternalId".
            email: Email address. Must be an exact match. Maps to
                "Email".
            alternative_email: Alternative email address. Must be an
                exact match. Maps to "AlternativeEmail".
            active: Filter on active/inactive contacts. Maps to
                "Active".
            categories: List of categories, identified by code name (in
                the configured language) or recno (e.g. "recno:123").
                Maps to "Categories".
            page: Pagination page number, 0-indexed. Defaults to 0.
                Should be used together with sort_criterion for a
                stable result order across pages.
            max_rows: Max number of contacts to return per page.
                Defaults to all.
            sort_criterion: "RecnoAscending" or "RecnoDescending",
                applied before page/max_rows.
            **extra_query: Any other GetContactPersonParameter field to
                pass through as-is (e.g. CreatedDateRange,
                ModifiedDateRange, DateCriteria, Web, AdditionalFields,
                AdditionalListFields, IncludeCustomFields). See the SIF
                API documentation, chapter "4.7 GetContactPersons", for
                the full list of fields.

        Returns:
            The parsed JSON GetContactPersonResult, e.g.
            {"ContactPersons": [...], "TotalCount": ...,
            "TotalPageCount": ..., "Successful": ...}. Each entry is a
            ContactPersonResult object (Recno, FirstName, LastName,
            ExternalId, Email, ...).

        Raises:
            ValueError: if no search criterion was supplied at all
                (GetContactPersons requires at least one).
        """
        if not name and not recno and not external_id and not email and not alternative_email and not categories and not extra_query:
            raise ValueError(
                "get_contact_persons requires at least one search criterion "
                "(name, recno, external_id, email, alternative_email, "
                "categories, or another GetContactPersonParameter field "
                "passed via extra_query)."
            )

        query: dict = {}
        if name:
            query["Name"] = name
        if recno:
            query["Recno"] = recno
        if external_id:
            query["ExternalId"] = external_id
        if email:
            query["Email"] = email
        if alternative_email:
            query["AlternativeEmail"] = alternative_email
        if active is not None:
            query["Active"] = active
        if categories:
            query["Categories"] = categories
        if page is not None:
            query["Page"] = page
        if max_rows is not None:
            query["MaxRows"] = max_rows
        if sort_criterion:
            query["SortCriterion"] = sort_criterion
        query.update(extra_query)

        response = self.post(
            f"{self.base_endpoint}/ContactService/GetContactPersons",
            json={"parameter": query},
        )
        return response.json()
    # *****************************************************************************************************************
    # *****************************************************************************************************************
    # *****************************************************************************************************************
    # *****************************************************************************************************************
    # *****************************************************************************************************************
    # *****************************************************************************************************************
    # *****************************************************************************************************************
    def sif_call(self, service: str, method: str, parameter: dict | None = None) -> dict:
        """Call any SIF RPC method and return the JSON response."""
        resp = self.post(
            f"{self.base_endpoint}/{service}/{method}",
            json={"parameter": parameter or {}},
        )
        data = resp.json()
        # SIF returns HTTP 200 even on business errors - check "Successful"
        if data.get("Successful") is False:
            raise RuntimeError(f"SIF error: {data.get('ErrorMessage')} | {data.get('ErrorDetails')}")
        return data
        
    def create_case(self, title, responsible_recno, archive_codes, case_type, status,
                    access_code=None, external_id=None):
        parameter = {
            "Title": title,
            "UnofficialTitle": title,
            "CaseType": case_type,
            "Status": status,
            "ResponsiblePersonRecno": responsible_recno,
            "ArchiveCodes": [
                {"Sort": i, "ArchiveType": t, "ArchiveCode": c}
                for i, (t, c) in enumerate(archive_codes, start=1)
            ],
        }
        if access_code:
            parameter["AccessCode"] = access_code
        if external_id:
            parameter["ExternalId"] = {"Id": external_id, "Type": "MyIntegration"}
        return self.sif_call("CaseService", "CreateCase", parameter)

    def create_document(self, title, case_number, filepath, category, status,
                        responsible_recno=None):
        path = Path(filepath)
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        parameter = {
            "Title": title,
            "CaseNumber": case_number,
            "Category": category,
            "Status": status,
            "Files": [{
                "Title": path.name,
                "Format": path.suffix[1:],
                "Base64Data": data,
            }],
        }
        if responsible_recno:
            parameter["ResponsiblePersonRecno"] = responsible_recno
        return self.sif_call("DocumentService", "CreateDocument", parameter)

if __name__ == "__main__":
    # Values below come from Tieto (realm_url, client_id) and from your
    # own tenant (tenant_host). See the class docstring for details.
    client = Public360Client(
        realm_url="https://keycloak.360online.com/realms/<customer-realm>",
        client_id="<bootstrap-client-id>",
        tenant_host="<customer>.public360online.com",
    )

    # Run once, interactively, to obtain the offline token:
    #   client.bootstrap()

    # Subsequent runs only need this - it transparently handles token
    # exchange, refresh, and retries:
    #   response = client.get("/some/api/path")
    #   print(response.json())
