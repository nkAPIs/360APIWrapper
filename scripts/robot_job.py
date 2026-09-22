"""
robot_job.py

Eksempel på et UBEMANDET, automatisk job (cron / scheduled task /
Windows-tjeneste) der kalder 360 API'et. Kræver INGEN interaktiv login -
den forudsætter, at bootstrap_once.py allerede er kørt, og at
TOKEN_STORAGE_PATH peger på den offline-token-fil, det producerede.

Kør fra repo-roden, fx via cron/scheduler:
    uv run python scripts/robot_job.py
"""

import sys

from src.public360_client import Public360AuthError, Public360Client

# Skal matche de værdier bootstrap blev kørt med.
REALM_URL = "https://keycloak.360online.com/realms/<customer-realm>"
CLIENT_ID = "<bootstrap-client-id>"
TENANT_HOST = "<kommune>.public360online.com"
TOKEN_STORAGE_PATH = "/sikker/sti/fk-api-offline-token.json"


def main() -> int:
    client = Public360Client(
        realm_url=REALM_URL,
        client_id=CLIENT_ID,
        tenant_host=TENANT_HOST,
        token_storage_path=TOKEN_STORAGE_PATH,
    )

    try:
        response = client.get("/some/api/path")
    except Public360AuthError as exc:
        # Offline-tokenet er ugyldigt (tilbagekaldt/udløbet/rettigheder
        # ændret). Der er ingen automatisk vej videre herfra - der SKAL
        # køres et nyt, manuelt bootstrap_once.py af en administrator.
        print(f"Authentikering fejlede, kræver manuel re-bootstrap: {exc}", file=sys.stderr)
        # TODO: send alarm/notifikation til drift/administrator her.
        return 1

    print(response.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
