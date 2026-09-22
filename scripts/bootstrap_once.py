"""
bootstrap_once.py

Kør dette script MANUELT og INTERAKTIVT, én gang, af et menneske med
adgang til en browser og en gyldig FK-servicebruger. Det åbner en
login-side hos FK Adgangsstyring og gemmer det resulterende offline
token i den fil, robotten/automatiseringen senere skal læse fra.

Skal IKKE indgå i et automatisk/ubemandet job - se scripts/robot_job.py
for det formål.

Kør fra repo-roden:
    uv run python scripts/bootstrap_once.py
"""

from src.public360_client import Public360Client

# Udfyld med værdierne fra Tieto og jeres eget tenant - se AUTHENTICATE.md.
REALM_URL = "https://keycloak.360online.com/realms/<customer-realm>"
CLIENT_ID = "<bootstrap-client-id>"
TENANT_HOST = "<kommune>.public360online.com"

# Sti hvor offline-tokenet gemmes. Flyt denne fil til jeres sikre
# secret store / til det miljø robotten kører i, når bootstrap er
# gennemført.
TOKEN_STORAGE_PATH = "./fk-api-offline-token.local.json"


def main() -> None:
    client = Public360Client(
        realm_url=REALM_URL,
        client_id=CLIENT_ID,
        tenant_host=TENANT_HOST,
        token_storage_path=TOKEN_STORAGE_PATH,
    )

    print("Starter bootstrap - en browser åbnes, log ind via FK Adgangsstyring...")
    client.bootstrap()
    print(
        f"Færdig. Offline token er gemt i: {TOKEN_STORAGE_PATH}\n"
        "Flyt/beskyt denne fil i jeres godkendte secret store, og peg "
        "robotten på den samme placering. Dette script skal ikke køres "
        "igen, medmindre tokenet bliver ugyldigt."
    )


if __name__ == "__main__":
    main()
