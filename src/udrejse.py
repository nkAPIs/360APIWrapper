"""
udrejse.py

Opslag af borgersager i 360 ud fra CPR-nummer.
"""

from typing import Optional, Union

from src.config import get_configuration
from src.public360_client import CaseType, Public360Client


class Udrejse:
    def __init__(self, env: str = "test", client: Optional[Public360Client] = None):
        """
        Args:
            env: "test" eller "prod" - vælger konfiguration (realm, client_id,
                tenant og offline token) via get_configuration, som i test.py.
            client: En færdig Public360Client. Hvis angivet, bruges den i
                stedet for at bygge en ud fra `env`.
        """
        if env not in ("test", "prod"):
            raise ValueError(f'env skal være "test" eller "prod", ikke "{env}".')
        self.env = env

        if client is None:
            config = get_configuration(debugmode=env == "test")
            client = Public360Client(
                realm_url=config.realm_url,
                client_id=config.client_id,
                tenant_host=config.tenant_host,
                token=config.token,
            )
        self.client = client

    def get_case_for_citizen(
        self,
        cpr: str,
        case_type: Optional[Union[str, CaseType]] = "Borgersag",
        title_contains: Optional[str] = "Udrejse",
    ) -> dict:
        """
        Find borgerens sager ud fra CPR-nummer, sagstype og titel.

        Args:
            cpr: CPR-nummer, med eller uden bindestreg ("010100-1234" eller
                "0101001234"). Sendes til 360 som 10 cifre.
            case_type: Sagstype som kode (fx "Borgersag"), "recno:<n>" eller
                et CaseType-medlem. None søger på tværs af sagstyper.
            title_contains: Tekst, som sagens titel skal indeholde (uden
                forskel på store og små bogstaver). None søger uanset titel.

        Returns:
            GetCasesResult fra CaseService/GetCases, fx
            {"Cases": [...], "TotalCount": ..., "Successful": True, ...}.
            "Cases" er tom, hvis ingen af borgerens sager matcher.
        """
        cpr = cpr.replace("-", "").replace(" ", "")
        if len(cpr) != 10 or not cpr.isdigit():
            raise ValueError("cpr skal bestå af 10 cifre.")

        extra_query = {}
        if title_contains:
            extra_query["Title"] = f"%{title_contains}%"

        result = self.client.get_cases(
            cpr_number=cpr,
            case_type=case_type,
            **extra_query,
        )
        # SIF returns HTTP 200 even on business errors - check "Successful"
        if result.get("Successful") is False:
            raise RuntimeError(
                f"SIF error: {result.get('ErrorMessage')} | {result.get('ErrorDetails')}"
            )
        return result
