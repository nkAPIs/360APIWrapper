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

from src.public360_client import Public360AuthError, Public360Client

ENVIRONMENTS = {
    "test": {
        "realm_url": "https://keycloak.360online.com/realms/naestved-test",
        "client_id": "naestved-test__edoc-api-bootstrap-cli",
        # TODO: confirm the actual TEST tenant hostname with Tieto if this differs.
        "tenant_host": "naestved.public360online.com",
        "token_storage_path": "./naestved-test-offline-token.local.json",
    },
    "prod": {
        "realm_url": "https://keycloak.360online.com/realms/naestved",
        # NOTE: Tieto supplied the same client id for both TEST and PROD.
        # Double-check this is intentional - normally each environment
        # gets its own bootstrap client id.
        "client_id": "naestved-test__edoc-api-bootstrap-cli",
        # TODO: confirm the actual PROD tenant hostname with Tieto if this differs.
        "tenant_host": "naestved.public360online.com",
        "token_storage_path": "./naestved-prod-offline-token.local.json",
    },
}

# Read-only RPC call used to confirm the token/endpoint chain works.
# Adjust with --api-path if AccessGroupService is not enabled on the
# endpoint configured in 360 web admin.
DEFAULT_API_PATH = "/Biz/v2/api/call/SI.Data.RPC/SI.Data.RPC/AccessGroupService/GetAccessGroups"


def run_test(env_name: str, api_path: str) -> int:
    # Step 1: look up the realm/client/tenant config for the chosen
    # environment (ENVIRONMENTS above) and build a client around it.
    # Nothing is sent over the network yet - this just prepares the
    # client with the values needed for later requests.
    config = ENVIRONMENTS[env_name]
    client = Public360Client(
        realm_url=config["realm_url"],
        client_id=config["client_id"],
        tenant_host=config["tenant_host"],
        token_storage_path=config["token_storage_path"],
    )

    print(f"[{env_name}] realm: {config['realm_url']}")
    print(f"[{env_name}] client_id: {config['client_id']}")
    print(f"[{env_name}] tenant: {config['tenant_host']}")

    # Step 2: check whether we already have an offline token cached on
    # disk from a previous run (config["token_storage_path"]). If not,
    # run bootstrap(): this fetches Keycloak's OpenID configuration,
    # starts an OAuth 2.0 Device Authorization Grant + PKCE flow, opens
    # a browser for you to log in via FK Adgangsstyring, and - once you
    # complete that login - stores the resulting offline token to disk.
    # This is the only step that requires a human in the loop.
    try:
        client._load_offline_token()
        print(f"[{env_name}] existing offline token found, skipping bootstrap.")
    except Public360AuthError:
        print(f"[{env_name}] no offline token found, starting bootstrap (browser will open)...")
        client.bootstrap()

    # Step 3: make one API call to prove the chain works end-to-end.
    # Under the hood, client.post() will: load the offline token,
    # exchange it for a short-lived access token via Keycloak's
    # refresh_token grant, attach it as "Authorization: Bearer ..." on
    # the request, and retry automatically on 401/429/5xx per the
    # integration guide's baseline (see public360_client.py).
    print(f"[{env_name}] calling {api_path} ...")
    try:
        response = client.post(api_path, json={})
    except Public360AuthError as exc:
        # The offline token was rejected (revoked/expired/etc). There is
        # no automatic recovery - a human must re-run bootstrap().
        print(f"[{env_name}] FAILED - authentication error: {exc}", file=sys.stderr)
        return 1

    # Step 4: report the result so a human can eyeball that the call
    # actually reached 360 and got real data back, not just a 200.
    print(f"[{env_name}] OK - HTTP {response.status_code}")
    print(response.json())
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
    return run_test("test", DEFAULT_API_PATH)



if __name__ == "__main__":
    raise SystemExit(main())
