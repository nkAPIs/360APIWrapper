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

def paragraf3_test(client, create: bool = False):
    ejendom = Ejendom("Næstvedvej", "25", "1234", "Andeby",
                      "517k", "Ande By, Dammen", lokalitetsnavn="Moserup")
    beskyttelser = [Beskyttelse.BESKYTTET_NATUR, Beskyttelse.STEN_OG_JORDDIGE]

    # Dry run: show what would be sent to 360
    print("Titel:", byg_titel(ejendom, beskyttelser))
    print("ArchiveCodes:", byg_archive_codes(client, beskyttelser))
    if not create:
        return

    me = find_person_recno(client, email="lakas@naestved.dk")
    r = opret_paragraf3_sag(client, ejendom, beskyttelser, responsible_recno=me)
    print("Created case:", r.get("CaseNumber"), "Recno:", r.get("Recno"))

    # Read it back to confirm the archive codes landed as expected
    check = client.sif_call("CaseService", "GetCases", {"Recno": r["Recno"]})
    case = check["Cases"][0]
    print(case.get("Title"))
    print(json.dumps(case.get("ArchiveCodes"), indent=2, ensure_ascii=False))



# ENVIRONMENTS = {
#     "test": {
#         "realm_url": "https://keycloak.360online.com/realms/naestved-test",
#         "client_id": "naestved-test__edoc-api-bootstrap-cli",
#         "tenant_host": "naestved.public360online.com",
#         "token_storage_path": "./naestved-test-offline-token.local.json",
#     },
#     "prod": {
#         "realm_url": "https://keycloak.360online.com/realms/naestved",
#         "client_id": "naestved__edoc-api-bootstrap-cli",
#         "tenant_host": "naestved.public360online.com",
#         "token_storage_path": "./naestved-prod-offline-token.local.json",
#     },
# }

# Read-only RPC call used to confirm the token/endpoint chain works.
# Adjust with --api-path if AccessGroupService is not enabled on the
# endpoint configured in 360 web admin.
# DEFAULT_API_PATH = "/Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC/AccessGroupService/GetAccessGroups"


def run_test(env_name: str, api_path: str=None) -> int:
    # Step 1: look up the realm/client/tenant config for the chosen
    # environment (ENVIRONMENTS above) and build a client around it.
    # Nothing is sent over the network yet - this just prepares the
    # client with the values needed for later requests.
    # config = ENVIRONMENTS[env_name]
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

    # Step 2: check whether we already have an offline token cached on
    # disk from a previous run (config["token_storage_path"]). If not,
    # run bootstrap(): this fetches Keycloak's OpenID configuration,
    # starts an OAuth 2.0 Device Authorization Grant + PKCE flow, opens
    # a browser for you to log in via FK Adgangsstyring, and - once you
    # complete that login - stores the resulting offline token to disk.
    # This is the only step that requires a human in the loop.
    # # # # try:
    # # # #     client._load_offline_token()
    # # # #     print(f"[{env_name}] existing offline token found, skipping bootstrap.")
    # # # # except Public360AuthError:
    # # # #     print(f"[{env_name}] no offline token found, starting bootstrap (browser will open)...")
    # # # #     client.bootstrap()

    # Step 3: make one API call to prove the chain works end-to-end.
    # Under the hood, client.post() will: load the offline token,
    # exchange it for a short-lived access token via Keycloak's
    # refresh_token grant, attach it as "Authorization: Bearer ..." on
    # the request, and retry automatically on 401/429/5xx per the
    # integration guide's baseline (see public360_client.py).
    #print(f"[{env_name}] calling {api_path} ...")
    print(f"pinging ...")
    try:
        response = client.ping()
    except Public360AuthError as exc:
        # The offline token was rejected (revoked/expired/etc). There is
        # no automatic recovery - a human must re-run bootstrap().
        print(f"[{env_name}] FAILED - authentication error: {exc}", file=sys.stderr)
        return 1

    # Step 4: report the result so a human can eyeball that the call
    # actually reached 360 and got real data back, not just a 200.
    print(f"[{env_name}] OK - HTTP {response.status_code}")
    print(response.json())

    paragraf3_test(client, create=True)

    if False:
        find_enterprises(client)
        get_document_stuff(client) 
        get_cases_test(client)  
        create_case_test(client)  
        create_case_test(client, filename="/Users/lakas/git/DataProccesor/README.pdf")

        print("********* END TEST **************************")    
        # res = client.sif_call("CaseService", "GetCases", {"Recno": 804386})
        # print(json.dumps(res, indent=2, ensure_ascii=False)[:4000])
        
        #   # later, look it back up by that same key:
        # result = client.get_cases(external_id="12300004444", external_id_type="AcmeSystem")
        result = client.sif_call("CaseService", "GetCases", { 
                                                            "CaseNumber":"85.15.00-P20-4-21S"
                                                            })
    # classification codes.
    print("classification codes.#################################################################################")
    res = client.sif_call("SupportService", "GetCodeTableRows",
               {"CodeTableName": "Noark Classification type"})
    # Show the raw response once so we know the structure
    print(json.dumps(res, indent=2, ensure_ascii=False)[:1500])
    
    print("classification codes.#################################################################################")
    res = client.sif_call("SupportService", "GetCodeTableRows",
               {
                   "CodeTableName": "Noark Classification type",
                    "Code": "85.15",
                    "IncludeParentClass": True,
                    "IncludeSubClasses": True,
                    "IncludeCustomFields": True
                }
            )


    
    
    # Show the raw response once so we know the structure
    print(json.dumps(res, indent=2, ensure_ascii=False)[:1500])


    # case types
    print("case types.#################################################################################")
    res = client.sif_call("SupportService", "GetCodeTableRows",
                {"CodeTableName": "code table: Case type"})
    print(json.dumps(res, indent=2, ensure_ascii=False)[:3000])

    # Status
    print("Status.#################################################################################")
    res = client.sif_call("SupportService", "GetCodeTableRows",
               {"CodeTableName": "code table: Case status"})
    for row in res.get("CodeTableRows", []):
        if not row.get("IsExpired"):
            print(row["Recno"], "|", row["Code"], "|", row["Description"])


    
    print("archive codes .#################################################################################")
    rows = res.get("CodeTableRows") or res.get("Rows") or []
    for row in rows:
        if row.get("Code") == "85.15.XX":
            print(row.get("Recno"), "|", row.get("Code"), "|", row.get("Description"))
    
    
    
    
    
    case = result["Cases"][0]
    for k, v in case.items():
        if "type" in k.lower():
            print(k, "=", v)
   # print(json.dumps(case, indent=4, ensure_ascii=False))
    print(json.dumps(case.get("ArchiveCodes"), indent=2, ensure_ascii=False))



    for recno in[500708]:
        try:
            result = client.create_case(
                title="Testsag oprettet via SIF API",
                responsible_recno=637056,          # Recno of the case handler
                case_type="recno:300001",
                status="recno:300001",
                archive_codes=[
                    (f"recno:{recno}", "85.15.00"),   # Recno of the right 85.15.XX row
                    ("Facet",       "P20"),        # use recno:… here too if Facet is also ambiguous
                ],    )
            
            print("Created case:", result.get("CaseNumber"), "Recno:", result.get("Recno"))
            print(json.dumps(result, indent=4, ensure_ascii=False))
        except Exception as e:
            print("EXCEPTION: ***************************************************************************")
            print(e)
 
    #print(sif_call("CaseService", "GetCases", {"CaseNumber": result.get("CaseNumber")}))
    
    ## 161026-- Created case: None Recno: 804383
    ## Created case: None Recno: 804386
    # Created case: None Recno: 804386
    # {
    #     "Recno": 804386,
    #     "CaseNumber": null,
    #     "ImportedCaseNumber": null,
    #     "UID": null,
    #     "UIDOrigin": null,
    #     "URL": null,
    #     "Successful": true,
    #     "ErrorMessage": "",
    #     "ErrorDetails": null
    # }




    return 0



def main() -> int:
    # Parse --env (which bootstrap client/environment to test) and the
    # optional --api-path override, then hand off to run_test().
    # parser = argparse.ArgumentParser(description=__doc__)
    # parser.add_argument(
    #     "--env",
    #     choices=sorted(ENVIRONMENTS),
    #     required=True,
    #     help="Which bootstrap client to test.",
    # )
    # parser.add_argument(
    #     "--api-path",
    #     default=DEFAULT_API_PATH,
    #     help="API path to call after authenticating (default: %(default)s).",
    # )
    # args = parser.parse_args()

    # return run_test(args.env, args.api_path)    
    return run_test("test", api_path=None)



if __name__ == "__main__":
    raise SystemExit(main())
