"""Django email backend that sends through Microsoft Graph from one school mailbox.

IT setup: give the app registration the *application* permission Mail.Send, grant admin
consent, and restrict it to the service mailbox with an Exchange application access policy.
"""

import logging

import msal
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

log = logging.getLogger(__name__)
GRAPH = "https://graph.microsoft.com/v1.0"


def _token() -> str:
    app = msal.ConfidentialClientApplication(
        settings.MS_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{settings.MS_TENANT_ID}",
        client_credential=settings.MS_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Graph token error: {result.get('error_description')}")
    return result["access_token"]


def _payload(message) -> dict:
    html = next(
        (content for content, mime in getattr(message, "alternatives", []) if mime == "text/html"),
        None,
    )
    return {
        "message": {
            "subject": message.subject,
            "body": {"contentType": "HTML" if html else "Text", "content": html or message.body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in message.to],
            "replyTo": [{"emailAddress": {"address": a}} for a in message.reply_to],
        },
        "saveToSentItems": True,
    }


class GraphEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        token = _token()
        url = f"{GRAPH}/users/{settings.GRAPH_SENDER_MAILBOX}/sendMail"
        sent = 0
        for message in email_messages:
            resp = requests.post(
                url,
                json=_payload(message),
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
            if resp.status_code == 202:
                sent += 1
            else:
                log.error("Graph sendMail failed %s: %s", resp.status_code, resp.text[:500])
                if not self.fail_silently:
                    resp.raise_for_status()
        return sent
