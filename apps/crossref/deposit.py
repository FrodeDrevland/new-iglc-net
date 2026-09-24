"""Sending a deposit to Crossref and reading its result.

    deposit = make(conference, papers, user)   # stored, not sent
    send(deposit)                              # HTTPS POST to Crossref (test or live)
    check(deposit)                             # fetches the result once Crossref has processed it

Crossref processes deposits in a queue: the result is usually there within minutes, sometimes
hours. Settings: CROSSREF_LOGIN, CROSSREF_PASSWORD, CROSSREF_TEST (the test system unless set
to false), CROSSREF_DEPOSITOR_NAME and _EMAIL (Crossref emails results there too).
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import uuid
from xml.etree import ElementTree as ET

from django.conf import settings
from django.utils import timezone

from .models import Deposit
from .xml import conference_xml

LIVE, TEST = "https://doi.crossref.org", "https://test.crossref.org"


class DepositError(Exception):
    pass


def configured() -> bool:
    return bool(settings.CROSSREF_LOGIN and settings.CROSSREF_PASSWORD)


def host(test: bool) -> str:
    return TEST if test else LIVE


def make(conference, papers, user=None, isbn: str = "") -> Deposit:
    papers = [p for p in papers if p.doi]
    batch_id, xml = conference_xml(conference, papers, isbn=isbn)
    return Deposit.objects.create(conference=conference, batch_id=batch_id, user=user, test=settings.CROSSREF_TEST,
                                  xml=xml.decode("utf-8"), papers=len(papers))


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, (filename, data) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                     f"Content-Type: application/xml\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def send(deposit: Deposit, opener=urllib.request.urlopen) -> Deposit:
    if not configured():
        raise DepositError("Crossref login is not set up on the server (CROSSREF_LOGIN, CROSSREF_PASSWORD)")
    if deposit.status != Deposit.Status.MADE:
        raise DepositError("This deposit has been sent already; make a new one")
    body, content_type = _multipart(
        {"operation": "doMDUpload", "login_id": settings.CROSSREF_LOGIN, "login_passwd": settings.CROSSREF_PASSWORD},
        {"fname": (deposit.file_name, deposit.xml.encode("utf-8"))})
    request = urllib.request.Request(f"{host(deposit.test)}/servlet/deposit", data=body, method="POST",
                                     headers={"Content-Type": content_type})
    try:
        with opener(request, timeout=60) as response:
            text = response.read().decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001 - shown to the publisher
        raise DepositError(f"Crossref could not be reached: {error}")
    deposit.response = text[:5000]
    if "SUCCESS" not in text.upper():
        deposit.save(update_fields=["response"])
        raise DepositError("Crossref did not accept the upload: " + " ".join(text.split())[:300])
    deposit.status, deposit.sent = Deposit.Status.SENT, timezone.now()
    deposit.save(update_fields=["response", "status", "sent"])
    return deposit


def check(deposit: Deposit, opener=urllib.request.urlopen) -> Deposit:
    """Fetch the result; the deposit stays 'sent' while Crossref has not processed it."""
    if deposit.status == Deposit.Status.MADE:
        raise DepositError("This deposit has not been sent")
    query = urllib.parse.urlencode({"usr": settings.CROSSREF_LOGIN, "pwd": settings.CROSSREF_PASSWORD,
                                    "file_name": deposit.file_name, "type": "result"})
    try:
        with opener(f"{host(deposit.test)}/servlet/submissionDownload?{query}", timeout=60) as response:
            text = response.read().decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001
        raise DepositError(f"Crossref could not be reached: {error}")
    deposit.checked, deposit.result = timezone.now(), text[:200000]
    read_result(deposit, text)
    deposit.save()
    return deposit


def read_result(deposit: Deposit, text: str):
    """doi_batch_diagnostic: record_diagnostic status Success/Warning/Failure per DOI, and batch_data counts."""
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return  # not processed yet (Crossref answers with a message)
    if root.tag.split("}")[-1] != "doi_batch_diagnostic" or root.get("status") not in ("completed",):
        return
    records = [r.get("status", "") for r in root.iter() if r.tag.split("}")[-1] == "record_diagnostic"]
    deposit.successes = sum(1 for r in records if r == "Success")
    deposit.warnings = sum(1 for r in records if r == "Warning")
    deposit.failures = sum(1 for r in records if r == "Failure")
    if deposit.failures:
        deposit.status = Deposit.Status.FAILED
    elif deposit.warnings:
        deposit.status = Deposit.Status.WARNING
    else:
        deposit.status = Deposit.Status.SUCCESS


def problems(text: str) -> list[tuple[str, str]]:
    """(DOI, message) of the records that did not succeed, from a result."""
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return []
    found = []
    for record in root.iter():
        if record.tag.split("}")[-1] == "record_diagnostic" and record.get("status") != "Success":
            doi = next((c.text for c in record if c.tag.split("}")[-1] == "doi"), "")
            message = next((c.text for c in record if c.tag.split("}")[-1] == "msg"), "")
            found.append((doi or "", message or ""))
    return found
