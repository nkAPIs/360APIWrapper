"""
test.py

Smoke test for the two Naestved bootstrap clients created in Keycloak
(see AUTHENTICATE.md for the full flow). Run this manually, from a
machine where you can open a browser, to confirm that a given
environment's bootstrap client works end-to-end:

    1. Discover the realm's OpenID configuration.
    2. Run the interactive device-code bootstrap once (skipped if an
       offline token is already stored for that environment).
    3. Exchange the offline token for an access token and make one
       read-only API call to confirm the whole chain works.

Usage:
    uv run python test.py --env test
    uv run python test.py --env prod
    uv run python test.py --env test --api-path /Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC/CaseService/GetCases

The offline token obtained for each environment is cached locally in
its own file (see ENVIRONMENTS below) so re-running this script does
not require logging in again. These files hold a secret equivalent to
a password - do not commit them (already covered by .gitignore).
"""

import argparse
import sys
from xmlrpc import client
import json
from src.config import get_configuration
from src.public360_client import Public360AuthError, Public360Client, DocumentCategory,DocumentStatus
from confighandler.src.configuration import Configuration
from src.public360_client import AccessGroup, CaseStatus, CaseType
from src.paragraf3_sager import Beskyttelse, Ejendom, byg_archive_codes, byg_titel, opret_paragraf3_sag
#from random import *
from pathlib import Path
from src.udrejse import Udrejse

def get_document_stuff(client):
    doc_result = client.get_document_categories()
    print(json.dumps(doc_result, indent=4))
    for cat in doc_result:
        print(f"{cat['Code']} # {cat['Description']} # {cat['Recno']}")
    
    doc_result = client.get_document_statuses()
    print(json.dumps(doc_result, indent=4))
    for cat in doc_result:
        print(f"{cat['Code']} # {cat['Description']} # {cat['Recno']}")
def find_person_recno(client, email:str=None, name:str=None):
    if not email and not name:
        return None

    recno = client.find_person_recno(name_or_email=email if email else name)
    print(f"recno for {email if email else name} is {recno}")
    return recno

def find_enterprises(client):
    result = client.get_enterprises(name='TID Systembrugere'
        # name: Optional[str] = None,
        # recno: Optional[str] = None,
        # external_id: Optional[str] = None,
        # enterprise_number: Optional[str] = None,
        # categories: Optional[list] = None,
        # active: Optional[bool] = None,
        # page: Optional[int] = None,
        # max_rows: Optional[int] = None,
        # sort_criterion: Optional[str] = None,
        # **extra_query,
    )
    
    print(json.dumps(result, indent=4))
    
def get_cases_test(client):
    try:
        print("#####################################################################################################")
        res = client.sif_call("CaseService", "GetCases", { "CaseNumber":"85.15.00-P20-4-21S"})  # your existing case
        case = res["Cases"][0]

        keys = ["CaseType", "Status", "AccessCode", "AccessGroup", "Paragraph",
                "ResponsiblePersonRecno", "ResponsiblePersonInitials",
                "ResponsibleEnterpriseRecno", "ResponsibleEnterprise"]
        for k in keys:
            print(k, "=", case.get(k))
        print("#####################################################################################################")
        print("#####################################################################################################")
        res = client.sif_call("CaseService", "GetCases", { "Title":"Testsag oprettet via SIF API 3"})  # your existing case
        case = res["Cases"][0]

        keys = ["CaseType", "Status", "AccessCode", "AccessGroup", "Paragraph",
                "ResponsiblePersonRecno", "ResponsiblePersonInitials",
                "ResponsibleEnterpriseRecno", "ResponsibleEnterprise"]
        for k in keys:
            print(k, "=", case.get(k))

        print(case['ResponsiblePerson'])

        print("#####################################################################################################")
    except Exception as e:
        print(e)

def create_case_test(client, filename:str=None):
    me = find_person_recno(client, email="lakas@naestved.dk")
    r = client.create_case(
                    title=f"Testsag oprettet via SIF API-LKKA 291026",
                    responsible_recno=me,
                    case_type="recno:300001",
                    status="recno:300001",
                    archive_codes=[
                        (f"recno:500708", "85.15.00"),   # Recno of the right 85.15.XX row
                        ("Facet",       "G01"),        # use recno:… here too if Facet is also ambiguous
                    ],    )
    
   
    print(r)

    if filename:
        doc = client.create_document(
            title=Path(filename).name,
            case_number=r["CaseNumber"],
            filepath=filename,
            category=DocumentCategory.INTERNT,
            status=DocumentStatus.K,
            responsible_recno=me,
        )
        print(doc)

    check = client.sif_call("CaseService", "GetCases", {"Recno": r["Recno"]})
    print(json.dumps(check, indent=2, ensure_ascii=False)[:2000])
def find_something(client):
    # persons = client.get_all_persons(active = True, page_size= 2000)
    # with open("persons_prod.json", "w", encoding="utf-8") as f:
    #      json.dump(persons, f, indent=4, ensure_ascii=False)


    # enterprises = client.get_all_enterprises(page_size=400)
    # ## save the enterprises to a file for later inspection
    # with open("enterprises_prod.json", "w", encoding="utf-8") as f:
    #     json.dump(enterprises, f, indent=4, ensure_ascii=False)

    # case_types = client.get_all_case_types()
    # with open("case_types_prod.json", "w", encoding="utf-8") as f:
    #     json.dump(case_types, f, indent=4, ensure_ascii=False)

    print("find_something done")
    
    
def paragraf3_test(client, create: bool = False):
    ejendom = Ejendom(
        vejnavn = "Nævervejen",
        husnummer = "25",
        postnummer = "4700",
        by = "Næstved",
        matrikelnummer = "517k",
        ejerlav = "Næstved By, Næstved",
        lokalitetsnavn="Moserup",
        # Angives bfe_nummer, knyttes ejendommen til sagen (se find_or_create_estate).
        bfe_nummer=9074628,
        ejendomstype = "SFE"
    )# kode i "code table: Estate type": SFE, BPFG, Ejerlejlighed, BPV

                # # # # {
                # # # # "id": "169cbf6f3a7848cdeabc718a2bfd9eed53b6e5fb177ebb58e871e510a0a898d1",
                # # # # "EjerType": "Person",
                # # # # "temanavn": [
                # # # #     {
                # # # #     "emnenr": "01.05.08",
                # # # #     "filnavn": "Paragraf3Natur\\tmp\\9074628_Beskyttede naturtyper_179369855210984.jpg",
                # # # #     "temanavn": "Beskyttede naturtyper"
                # # # #     },
                # # # #     {
                # # # #     "emnenr": "01.05.25",
                # # # #     "filnavn": "Paragraf3Natur\\tmp\\9074628_Beskyttede sten- og jorddiger_17936985549864.jpg",
                # # # #     "temanavn": "Beskyttede sten- og jorddiger"
                # # # #     }
                # # # # ],
                # # # # "bfe_nummer": 9074628,
                # # # # "NavnJusteret": "Peter Strandgaard",
                # # # # "EjerensStatus": "bopael_i_danmark",
                # # # # "EjerStatusKode_T": "Hovedejer",
                # # # # "json_featuretype": "nye_ejere",
                # # # # "overtagelsesdato": "20260901",
                # # # # "matnr_ejerlavsnavn": "6a, Saltø By, Vallensved",
                # # # # "EjersAdresseDanmark": "Saltøvej 95, Saltø By, 4700 Næstved",
                # # # # "EjendePersonPersonNR": "2903650411",
                # # # # "EjendeVirksomhedCVRnr": null
                # # # # }
    
    beskyttelser = [Beskyttelse.BESKYTTET_NATUR, Beskyttelse.STEN_OG_JORDDIGE]

    # Dry run: show what would be sent to 360
    print("Titel:", byg_titel(ejendom, beskyttelser))
    print("ArchiveCodes:", byg_archive_codes(client, beskyttelser))
    if not create:
        return

    enterprise = client.get_enterprises(name="Center for Koncernservice")
    
    me = find_person_recno(client, email="lakas@naestved.dk")
    me2 =  525999
    
    r = opret_paragraf3_sag(
        client=client,
        ejendom=ejendom,
        beskyttelser=beskyttelser,
        responsible_recno=me,
        responsible_enterprise_recno = enterprise.get("Recno") if enterprise else None,
        casehandler_recno = me2,
        case_type = "Geosag",
        status = "recno:300001",
        access_code = "W",
        external_id = None
    )
    print("Created case:", r.get("CaseNumber"), "Recno:", r.get("Recno"))

    # Read it back to confirm the archive codes landed as expected
    check = client.sif_call("CaseService", "GetCases", {"Recno": r["Recno"]})
    case = check["Cases"][0]
    print(case.get("Title"))
    print(json.dumps(case.get("ArchiveCodes"), indent=2, ensure_ascii=False))

def run_test(env_name: str, api_path: str=None) -> int:
    config = get_configuration(debugmode=True if env_name == "test" else False)

    if api_path is None:
        api_path = config.DEFAULT_API_PATH
    
    client = Public360Client(
        realm_url=config.realm_url,
        client_id=config.client_id,
        tenant_host=config.tenant_host,
        token=config.token
        #token_storage_path=config.token_storage_path,
    )
    print(f"[{env_name}] realm: {config.realm_url}")
    print(f"[{env_name}] client_id: {config.client_id}")
    print(f"[{env_name}] tenant: {config.tenant_host}")

    print(f"pinging ...")
    try:
        response = client.ping()
    except Public360AuthError as exc:
        print(f"[{env_name}] FAILED - authentication error: {exc}", file=sys.stderr)
        return 1

    print(f"[{env_name}] OK - HTTP {response.status_code}")
    print(response.json())

    find_something(client)

    paragraf3_test(client, create=True)

#     # classification codes.
#     print("classification codes.#################################################################################")
#     res = client.sif_call("SupportService", "GetCodeTableRows",
#                {"CodeTableName": "Noark Classification type"})
#     # Show the raw response once so we know the structure
#     print(json.dumps(res, indent=2, ensure_ascii=False)[:1500])
    
#     print("classification codes.#################################################################################")
#     res = client.sif_call("SupportService", "GetCodeTableRows",
#                {
#                    "CodeTableName": "Noark Classification type",
#                     "Code": "85.15",
#                     "IncludeParentClass": True,
#                     "IncludeSubClasses": True,
#                     "IncludeCustomFields": True
#                 }
#             )


    
    
#     # Show the raw response once so we know the structure
#     print(json.dumps(res, indent=2, ensure_ascii=False)[:1500])


#     # case types
#     print("case types.#################################################################################")
#     res = client.sif_call("SupportService", "GetCodeTableRows",
#                 {"CodeTableName": "code table: Case type"})
#     print(json.dumps(res, indent=2, ensure_ascii=False)[:3000])

#     # Status
#     print("Status.#################################################################################")
#     res = client.sif_call("SupportService", "GetCodeTableRows",
#                {"CodeTableName": "code table: Case status"})
#     for row in res.get("CodeTableRows", []):
#         if not row.get("IsExpired"):
#             print(row["Recno"], "|", row["Code"], "|", row["Description"])


    
#     print("archive codes .#################################################################################")
#     rows = res.get("CodeTableRows") or res.get("Rows") or []
#     for row in rows:
#         if row.get("Code") == "85.15.XX":
#             print(row.get("Recno"), "|", row.get("Code"), "|", row.get("Description"))
    
    
    
    
    
#     case = result["Cases"][0]
#     for k, v in case.items():
#         if "type" in k.lower():
#             print(k, "=", v)
#    # print(json.dumps(case, indent=4, ensure_ascii=False))
#     print(json.dumps(case.get("ArchiveCodes"), indent=2, ensure_ascii=False))

#     for recno in[500708]:
#         try:
#             result = client.create_case(
#                 title="Testsag oprettet via SIF API",
#                 responsible_recno=637056,          # Recno of the case handler
#                 case_type="recno:300001",
#                 status="recno:300001",
#                 archive_codes=[
#                     (f"recno:{recno}", "85.15.00"),   # Recno of the right 85.15.XX row
#                     ("Facet",       "P20"),        # use recno:… here too if Facet is also ambiguous
#                 ],    )
            
#             print("Created case:", result.get("CaseNumber"), "Recno:", result.get("Recno"))
#             print(json.dumps(result, indent=4, ensure_ascii=False))
#         except Exception as e:
#             print("EXCEPTION: ***************************************************************************")
#             print(e)
 
    return 0



def main() -> int:
    return run_test("prod", api_path=None)

if __name__ == "__main__":
    #raise SystemExit(make_new_token(env_name="test", json_file="./naestved-parrob-test-offline-token.local.json"))
    raise SystemExit(main())
