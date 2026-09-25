"""Email backends.

Production sends through Azure Communication Services Email (AzureEmailBackend) and signs in with
the web app's managed identity, so there is no password or key to store or renew. See
docs/deploy-azure.md, "Email". Elsewhere mail goes over SMTP (EMAIL_HOST) or, by default, to the
log (ConsoleBackend).

All three add EMAIL_REPLY_TO to messages that have no Reply-To of their own, so replies to
password resets and error reports reach a person rather than noreply@.

Only the standard library is used: the managed identity token and the send are two HTTPS calls.
"""

import base64
import json
import logging
import os
import threading
import time
import uuid
from email.mime.base import MIMEBase
from email.utils import getaddresses, parseaddr
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as DjangoConsoleBackend
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend

logger = logging.getLogger(__name__)

# Token audience for Azure Communication Services (the same one Microsoft's SDK asks for).
ACS_RESOURCE = "https://communication.azure.com/"
ACS_API_VERSION = "2023-03-31"
# Headers Azure sets itself or that come from the message's own fields.
_RESERVED_HEADERS = {"from", "to", "cc", "bcc", "reply-to", "subject", "sender", "date", "message-id",
                     "mime-version", "content-type", "content-transfer-encoding", "return-path"}


def add_default_reply_to(email_messages) -> None:
    default = getattr(settings, "EMAIL_REPLY_TO", "")
    if default:
        for message in email_messages:
            if not message.reply_to:
                message.reply_to = [default]


class DefaultReplyToMixin:
    def send_messages(self, email_messages):
        add_default_reply_to(email_messages)
        return super().send_messages(email_messages)


class SMTPBackend(DefaultReplyToMixin, DjangoSMTPBackend):
    pass


class ConsoleBackend(DefaultReplyToMixin, DjangoConsoleBackend):
    pass


class EmailSendError(Exception):
    pass


_token_lock = threading.Lock()
_token_cache = {"token": "", "expires": 0.0}


def managed_identity_token() -> str:
    """An access token for Azure Communication Services from App Service's managed identity.

    App Service provides IDENTITY_ENDPOINT and IDENTITY_HEADER when the identity is switched on.
    Tokens last about a day; this keeps one until five minutes before it runs out.
    """
    with _token_lock:
        if _token_cache["token"] and _token_cache["expires"] - 300 > time.time():
            return _token_cache["token"]
        endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise EmailSendError("No managed identity: switch on the web app's identity "
                                 "(az webapp identity assign) or leave AZURE_EMAIL_ENDPOINT unset.")
        query = {"resource": ACS_RESOURCE, "api-version": "2019-08-01"}
        if os.environ.get("AZURE_CLIENT_ID"):  # only for a user-assigned identity
            query["client_id"] = os.environ["AZURE_CLIENT_ID"]
        request = Request(f"{endpoint}?{urlencode(query)}", headers={"X-IDENTITY-HEADER": header})
        try:
            with urlopen(request, timeout=10) as response:
                data = json.load(response)
        except (HTTPError, URLError) as error:
            raise EmailSendError(f"Could not get a managed identity token: {error}") from error
        _token_cache["token"] = data["access_token"]
        _token_cache["expires"] = float(data.get("expires_on") or time.time() + 600)
        return _token_cache["token"]


def _addresses(values) -> list[dict]:
    result = []
    for name, address in getaddresses(list(values)):
        if address:
            result.append({"address": address, "displayName": name} if name else {"address": address})
    return result


def _attachment(item) -> dict:
    if isinstance(item, MIMEBase):
        name, mimetype, content = item.get_filename() or "attachment", item.get_content_type(), item.get_payload(decode=True)
    else:
        name, content, mimetype = item[0], item[1], item[2]
    if isinstance(content, str):
        content = content.encode("utf-8")
    return {"name": name or "attachment", "contentType": mimetype or "application/octet-stream",
            "contentInBase64": base64.b64encode(content or b"").decode("ascii")}


def acs_payload(message) -> dict:
    """The JSON body for the emails:send call, from a Django EmailMessage."""
    content = {"subject": message.subject}
    if getattr(message, "content_subtype", "plain") == "html":
        content["html"] = message.body
    else:
        content["plainText"] = message.body
    for alternative in getattr(message, "alternatives", []) or []:
        body, mimetype = alternative[0], alternative[1]
        if mimetype == "text/html" and "html" not in content:
            content["html"] = body
    payload = {
        "senderAddress": parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)[1],
        "content": content,
        "recipients": {"to": _addresses(message.to), "cc": _addresses(message.cc), "bcc": _addresses(message.bcc)},
        "userEngagementTrackingDisabled": True,
    }
    if message.reply_to:
        payload["replyTo"] = _addresses(message.reply_to)
    headers = {k: str(v) for k, v in (message.extra_headers or {}).items() if k.lower() not in _RESERVED_HEADERS}
    if headers:
        payload["headers"] = headers
    if message.attachments:
        payload["attachments"] = [_attachment(item) for item in message.attachments]
    return payload


class AzureEmailBackend(BaseEmailBackend):
    """Sends through Azure Communication Services Email (settings.AZURE_EMAIL_ENDPOINT).

    Azure accepts the message (202) and delivers it shortly after. Throttling (429, when the
    domain's sending quota is used up) and other errors raise EmailSendError, or are logged
    with fail_silently.
    """

    def send_messages(self, email_messages):
        add_default_reply_to(email_messages)
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                self._send(message)
                sent += 1
            except EmailSendError:
                if not self.fail_silently:
                    raise
                logger.exception("Email %r to %s was not sent", message.subject, message.recipients())
        return sent

    def _send(self, message):
        endpoint = settings.AZURE_EMAIL_ENDPOINT.rstrip("/")
        body = json.dumps(acs_payload(message)).encode("utf-8")
        request = Request(
            f"{endpoint}/emails:send?api-version={ACS_API_VERSION}", data=body, method="POST",
            headers={"Authorization": f"Bearer {managed_identity_token()}",
                     "Content-Type": "application/json",
                     "x-ms-client-request-id": str(uuid.uuid4())})
        try:
            with urlopen(request, timeout=20) as response:
                if response.status not in (200, 202):
                    raise EmailSendError(f"Azure answered {response.status}")
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            if error.code == 429:
                raise EmailSendError(f"Sending quota used up (429), retry after "
                                     f"{error.headers.get('Retry-After', '?')} s: {detail}") from error
            raise EmailSendError(f"Azure answered {error.code}: {detail}") from error
        except URLError as error:
            raise EmailSendError(f"Could not reach Azure Communication Services: {error}") from error

