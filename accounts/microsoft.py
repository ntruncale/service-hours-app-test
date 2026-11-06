"""Microsoft Entra ID sign-in using MSAL's authorization-code flow.

Kept in its own module so tests can replace these two functions with fakes and never
call Microsoft.
"""

import msal
from django.conf import settings

SCOPES = ["User.Read"]


def _app() -> msal.ConfidentialClientApplication:
    if not (settings.MS_TENANT_ID and settings.MS_CLIENT_ID and settings.MS_CLIENT_SECRET):
        raise RuntimeError("Microsoft sign-in is not configured (MS_* environment variables).")
    return msal.ConfidentialClientApplication(
        settings.MS_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{settings.MS_TENANT_ID}",
        client_credential=settings.MS_CLIENT_SECRET,
    )


def start_flow(redirect_uri: str) -> dict:
    """Returns a flow dict; send the user to flow['auth_uri'] and keep the dict in the session."""
    return _app().initiate_auth_code_flow(
        SCOPES, redirect_uri=redirect_uri, prompt="select_account"
    )


def finish_flow(flow: dict, query_params: dict) -> dict:
    """Exchanges the code for tokens. MSAL checks state and nonce for us."""
    return _app().acquire_token_by_auth_code_flow(flow, query_params)
