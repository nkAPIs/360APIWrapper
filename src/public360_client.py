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
from typing import Optional

import requests


class Public360AuthError(Exception):
    """Raised when authentication with the 360 API fails and cannot be recovered automatically."""


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
        token_storage_path: str = "./fk-api-offline-token.local.json",
        timeout: float = 30.0,
    ):
        self.realm_url = realm_url.rstrip("/")
        self.client_id = client_id
        self.api_base_url = f"https://{tenant_host}"
        self.token_storage_path = token_storage_path
        self.timeout = timeout

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
        offline_token = self._load_offline_token()

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
        offline_token = self._load_offline_token()
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
