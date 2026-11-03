"""
paragraf3_sager.py

Oprettelse af § 3-natursager ("§ 3 Nye ejere af: ...") efter den aftalte
navngivning og KLE-klassifikation:

    Titel:  Vejnavn husnummer, postnummer by, [lokalitetsnavn,]
            matr.nr ejerlav (hovedhusmatriklen), sagstype
    KLE:    01.05.08 / 01.05.02 / 01.05.25 afhængigt af beskyttelsestype(r)
    Facet:  G01 Generelle sager

Både ArchiveType og ArchiveCode sendes som "recno:<Recno>", slået op ved
kørselstid i kodetabellerne "Noark Classification type" og
"Noark Classification code" (se find_archive_type / find_archive_code).
Kodetekst alene fejler for gruppekoder som "01.05" ("Invalid token or data
encountered! (01.05)"), fordi SIF's eget opslag ikke finder dem under typen.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from src.public360_client import Public360Client

CLASSIFICATION_TYPE_TABLE = "Noark Classification type"
CLASSIFICATION_CODE_TABLE = "Noark Classification code"
SUB_ARCHIVE_TABLE = "Noark Subarchive"  # "Hovedgruppe" i GUI'en

# Koder (ikke recnos) i CLASSIFICATION_TYPE_TABLE. I denne tenant er
# ArchiveType KLE-gruppen ("01.05.XX"), ikke "KLE" generelt.
KLE_GRUPPE_TYPE_KODE = "01.05.XX"  # Naturbeskyttelse
KLE_GRUPPE = "01.05"
FACET_TYPE_KODE = "Facet"
HANDLINGSFACET = "G01"  # Generelle sager

_table_cache: dict[tuple[int, str], list[dict]] = {}


def _find_recno(client: Public360Client, table: str, kode: str, prefix: bool = False) -> str:
    """
    Slå en kode op i en kodetabel og returnér den som "recno:<Recno>".
    Med prefix=True matches koder, der starter med `kode` (bruges til
    "Noark Subarchive", hvor koden er fx "01 Fysisk planlægning og ...").

    Nogle koder findes som flere aktive rækker (fx 01.05.XX som både 300031
    og 500031) - formentlig en ældre og en nyere KLE-import. Så vælges den
    højeste recno, svarende til at de koder, der virker ved oprettelse
    (500708, 504849, 505096), alle ligger i 500xxx-serien. Tabellerne
    hentes én gang pr. klient.

    include_expired_values=True er nødvendigt: uden det returnerer 360 kun
    en delmængde af "Noark Classification code" (1322 af 5424 rækker), og
    fx 01.05.08 mangler, selvom den har IsExpired=False. Vi filtrerer
    derfor selv på IsExpired.
    """
    key = (id(client), table)
    if key not in _table_cache:
        result = client.get_code_table_rows(table, include_expired_values=True)
        _table_cache[key] = result.get("CodeTableRows", [])
    matches = [
        row["Recno"]
        for row in _table_cache[key]
        if (row.get("Code", "").startswith(kode) if prefix else row.get("Code") == kode)
        and not row.get("IsExpired")
    ]
    if not matches:
        raise LookupError(f'"{kode}" findes ikke i "{table}".')
    return f"recno:{max(matches)}"


def find_archive_type(client: Public360Client, kode: str) -> str:
    """ArchiveType ud fra kode, fx "01.05.XX" eller "Facet"."""
    return _find_recno(client, CLASSIFICATION_TYPE_TABLE, kode)


def find_archive_code(client: Public360Client, kode: str) -> str:
    """ArchiveCode ud fra kode, fx "01.05", "01.05.08" eller "G01"."""
    return _find_recno(client, CLASSIFICATION_CODE_TABLE, kode)


def find_sub_archive(client: Public360Client, hovedgruppe: str) -> str:
    """SubArchive ("Hovedgruppe") ud fra KLE-hovedgruppe, fx "01"."""
    return _find_recno(client, SUB_ARCHIVE_TABLE, f"{hovedgruppe} ", prefix=True)


class Beskyttelse(Enum):
    """Beskyttelsestype -> (tekst i titlen, KLE-emnenummer)."""

    BESKYTTET_NATUR = ("Beskyttet natur", "01.05.08")
    AABESKYTTELSESLINJE = ("Ejendom inden for åbeskyttelseslinjen", "01.05.02")
    FORTIDSMINDEBESKYTTELSESLINJE = (
        "Ejendom inden for Fortidsmindebeskyttelseslinjen",
        "01.05.02",
    )
    STEN_OG_JORDDIGE = ("Ejendom med beskyttet sten- og jorddige", "01.05.25")

    @property
    def tekst(self) -> str:
        return self.value[0]

    @property
    def kle(self) -> str:
        return self.value[1]


@dataclass
class Ejendom:
    vejnavn: str
    husnummer: str
    postnummer: str
    by: str
    matrikelnummer: str  # hovedhusmatriklen, fx "517k"
    ejerlav: str  # fx "Næstved By, Næstved"
    lokalitetsnavn: Optional[str] = None


def byg_titel(ejendom: Ejendom, beskyttelser: Iterable[Beskyttelse]) -> str:
    """
    Fx: "Næstvedvej 25, 4700 Næstved, Moserup, 517k Næstved By, Næstved,
    § 3 Nye ejere af: Beskyttet natur/Ejendom med beskyttet sten- og jorddige"
    """
    dele = [
        f"{ejendom.vejnavn} {ejendom.husnummer}",
        f"{ejendom.postnummer} {ejendom.by}",
    ]
    if ejendom.lokalitetsnavn:
        dele.append(ejendom.lokalitetsnavn)
    dele.append(f"{ejendom.matrikelnummer} {ejendom.ejerlav}")
    dele.append("§ 3 Nye ejere af: " + "/".join(b.tekst for b in beskyttelser))
    return ", ".join(dele)


def byg_archive_codes(
    client: Public360Client, beskyttelser: Iterable[Beskyttelse]
) -> list[tuple[str, str]]:
    """
    Samme mønster som eksisterende 01.05.08-sager: gruppen "01.05", så
    KLE-emnerne (uden dubletter, da å- og fortidsmindebeskyttelseslinjen
    begge er 01.05.02), og til sidst handlingsfacetten. create_case sætter
    Sort ud fra listens rækkefølge.
    """
    gruppe_type = find_archive_type(client, KLE_GRUPPE_TYPE_KODE)
    facet_type = find_archive_type(client, FACET_TYPE_KODE)
    # 360-GUI'en læser ArchiveCodes positionelt: Sort 1 = Gruppe,
    # Sort 2 = Emneord, Sort 3 = Facet. Facetten skal derfor stå på plads 3;
    # ekstra emner kommer bagefter (gemmes på sagen, men vises ikke i GUI'en).
    emner = list(dict.fromkeys(b.kle for b in beskyttelser))
    gruppe = (gruppe_type, find_archive_code(client, KLE_GRUPPE))
    facet = (facet_type, find_archive_code(client, HANDLINGSFACET))
    return (
        [gruppe, (gruppe_type, find_archive_code(client, emner[0])), facet]
        + [(gruppe_type, find_archive_code(client, kode)) for kode in emner[1:]]
    )


def opret_paragraf3_sag(
    client: Public360Client,
    ejendom: Ejendom,
    beskyttelser: list[Beskyttelse],
    responsible_recno: int,
    case_type: str = "recno:300001",
    status: str = "recno:300001",
    access_code: Optional[str] = None,
    external_id: Optional[str] = None,
) -> dict:
    if not beskyttelser:
        raise ValueError("Mindst én beskyttelsestype skal angives.")

    return client.create_case(
        title=byg_titel(ejendom, beskyttelser),
        responsible_recno=responsible_recno,
        archive_codes=byg_archive_codes(client, beskyttelser),
        case_type=case_type,
        status=status,
        access_code=access_code,
        external_id=external_id,
        sub_archive=find_sub_archive(client, KLE_GRUPPE.split(".")[0]),
    )
