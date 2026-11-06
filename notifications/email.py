"""Send an email from a pair of templates: templates/emails/<name>.txt and .html.

The first line of the .txt template is the subject, e.g. "Subject: Please confirm ...".
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

log = logging.getLogger(__name__)


def send_templated_email(*, to, template, context, reply_to=None) -> None:
    context = {**context, "SCHOOL_NAME": settings.SCHOOL_NAME}
    text = render_to_string(f"emails/{template}.txt", context).strip()
    first, _, body = text.partition("\n")
    subject = first.removeprefix("Subject:").strip()
    html = render_to_string(f"emails/{template}.html", context)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=body.strip(),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
        reply_to=reply_to,
    )
    msg.attach_alternative(html, "text/html")
    try:
        msg.send()
    except Exception:  # an email outage must not lose the student's entry
        log.exception("Email to %s failed (template %s)", to, template)
