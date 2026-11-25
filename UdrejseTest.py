import sys
from xmlrpc import client
import json
from public360.src.config import get_configuration
from public360.src.public360_client import Public360AuthError, Public360Client, DocumentCategory,DocumentStatus
from confighandler.src.configuration import Configuration
from public360.src.public360_client import AccessGroup, CaseStatus, CaseType
from public360.src.paragraf3_sager import Beskyttelse, Ejendom, byg_archive_codes, byg_titel, opret_paragraf3_sag
#from random import *
from pathlib import Path
from public360.src.udrejse import Udrejse

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
        
        # Sagsnr.     Sagstitel       Sagstype        Sagsbehandler       Ansvarlig enhed     
        # 26-030086   NBB - Udrejse   Borgersag       Rana Mohamad Ahmad  Borgervejledningen
        
        
        print("#####################################################################################################")
        res = client.sif_call("CaseService", "GetCases", { "CaseNumber":"26-030086"})  # your existing case
        case = res["Cases"][0]

        keys = ["CaseType", "Status", "AccessCode", "AccessGroup", "Paragraph",
                "ResponsiblePersonRecno", "ResponsiblePersonInitials",
                "ResponsibleEnterpriseRecno", "ResponsibleEnterprise"]
        for k in keys:
            print(k, "=", case.get(k))
        print("#####################################################################################################")
    except Exception as e:
        print(e)

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
    
    
def find_udrejse_sager(client, env: str = "prod"):


    udrejse = Udrejse(env=env, client=client)
     

    if udrejse.citizens_has_open_case(cpr="0305058009"):
        print("har en sag!")
    else:
        print("har ikke en sag")
        



    result = udrejse.get_case_for_citizen(
        cpr = "0305058009",
        case_type = CaseType.CITIZEN_CASE,
        #title_contains = "Udrejse",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # print("*************************************************************'")
    # result = udrejse.get_case_for_citizen(
    #     cpr = "2402832986",
    #     case_type = CaseType.CITIZEN_CASE,
    #     title_contains = "Udrejse",
    # )
    # print(json.dumps(result, indent=2, ensure_ascii=False))
    # print("*************************************************************'")
    
    # result = udrejse.get_case_for_citizen(
    #     cpr = "2211125449",
    #     case_type = CaseType.CITIZEN_CASE,
    #     title_contains = "Udrejse",
    # )
    # print(json.dumps(result, indent=2, ensure_ascii=False))

    print("Done")

def run_test(env_name: str, api_path: str=None) -> int:
    config = get_configuration(debugmode=True if env_name == "test" else False)

    if api_path is None:
        api_path = config.DEFAULT_API_PATH
    
    client = Public360Client(
        realm_url=config.realm_url,
        client_id=config.client_id,
        tenant_host=config.tenant_host,
        token="eyJhbGciOiJIUzUxMiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJlMjZkMTk1Ni01OTIxLTQ2YzMtYTljOS1kYzE1ZWYyZjdmNTQifQ.eyJpYXQiOjE3OTQ0ODcwMTEsImp0aSI6IjM5NzM5OTJmLTQ0NTUtY2M4NC1lZTA0LTkxOTg0OGE3Yjc4OCIsImlzcyI6Imh0dHBzOi8va2V5Y2xvYWsuMzYwb25saW5lLmNvbS9yZWFsbXMvbmFlc3R2ZWQiLCJhdWQiOiJodHRwczovL2tleWNsb2FrLjM2MG9ubGluZS5jb20vcmVhbG1zL25hZXN0dmVkIiwic3ViIjoiZmQ0Y2MxNzYtODM3Ni00ZDhjLWJjNjEtMzBjZWZjNGQzYTY2IiwidHlwIjoiT2ZmbGluZSIsImF6cCI6Im5hZXN0dmVkX19lZG9jLWFwaS1ib290c3RyYXAtY2xpIiwic2lkIjoia0ozXzlRODJnWGx5b24xVTYxcks5LU1IIiwic2NvcGUiOiJvcGVuaWQgcmVhbG0tY2xhaW1zIG5hZXN0dmVkLWNsYWltcyBlbWFpbCBiYXNpYyBhY3Igb2ZmbGluZV9hY2Nlc3Mgd2ViLW9yaWdpbnMgcm9sZXMgcHJvZmlsZSIsImF1ZF94IjoiYWNjb3VudCIsInByb3YiOiJkZWZhdWx0In0.sgcd6sMcPbusq02PHuc4VKLdp6x1GuFK7AKP0RSnHKGuBzs-zhBTYnYmGXD-uEmPhEyeoszTC0bbdbMp4bJiAQ"#config.token
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

#    find_something(client)

 #   udrejse = Udrejse(env="prod", client=client)
  #  result = udrejse.get_case_for_citizen(
   #     cpr = "0505864107",
#        case_type = CaseType.CITIZEN_CASE,
#        title_contains = "Udrejse",
   # )
    #print(json.dumps(result, indent=2, ensure_ascii=False))


#    get_cases_test(client)


    find_udrejse_sager(client, env=env_name)

    return 0



def main() -> int:
    return run_test("prod", api_path=None)

if __name__ == "__main__":
    raise SystemExit(main())
