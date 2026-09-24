"""Adding papers' files: pairing Word files with PDFs, checking them, keeping every version."""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
import zipfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from .checks import PRODUCTION, check_paper
from .models import Event, PaperVersion, Submission


def paper_number(filename: str) -> int | None:
    """The ConfTool ID at the start of a file name: '123.docx', '123 edited.pdf', '0123_v2.docx'."""
    match = re.match(r"\D*?(\d+)", Path(filename).stem)
    return int(match.group(1)) if match else None


def expand(files) -> list[tuple[str, bytes]]:
    """(name, content) of the uploaded files, with ZIP files unpacked."""
    out = []
    for name, data in files:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    base = Path(info.filename).name
                    if not info.is_dir() and not base.startswith(("~$", ".")) and "__MACOSX" not in info.filename:
                        out.append((base, archive.read(info)))
        else:
            out.append((name, data))
    return out


def pair(files) -> tuple[dict[int, dict], list[str]]:
    """{ConfTool ID: {"docx": (name, bytes), "pdf": (name, bytes)}}, and the names not understood."""
    pairs, ignored = {}, []
    for name, data in expand(files):
        kind = Path(name).suffix.lower().lstrip(".")
        number = paper_number(name)
        if kind not in ("docx", "pdf") or number is None:
            ignored.append(name)
            continue
        pairs.setdefault(number, {})[kind] = (name, data)
    return pairs, ignored


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@transaction.atomic
def add_version(submission: Submission, docx: tuple[str, bytes] | None, pdf: tuple[str, bytes] | None,
                user=None, comment: str = "") -> PaperVersion:
    """A new version from a Word file and/or its PDF. A PDF alone goes with the current Word file."""
    current = submission.current
    if docx is None:
        if current is None:
            raise ValueError("A PDF needs its Word file: upload the Word file first, or both together")
        docx = (Path(current.docx.name).name.split("-", 1)[-1], current.docx.open("rb").read())
        current.docx.close()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "paper.docx"
        path.write_bytes(docx[1])
        result = check_paper(path, PRODUCTION, io.BytesIO(pdf[1]) if pdf else None)
    pages = None
    if pdf:
        try:
            from pypdf import PdfReader

            pages = len(PdfReader(io.BytesIO(pdf[1])).pages)
        except Exception:  # noqa: BLE001 - reported by the check
            pages = None
    number = (current.number + 1) if current else 1
    version = PaperVersion(
        submission=submission, number=number, uploaded_by=user, comment=comment,
        docx_sha256=_sha(docx[1]), pdf_sha256=_sha(pdf[1]) if pdf else "", pages=pages,
        metadata=result.manuscript.as_dict(), passed=result.passed,
        findings=[{"level": f.level, "code": f.code, "message": f.message} for f in result.findings],
    )
    version.docx.save(f"{submission.conftool_id}.docx", ContentFile(docx[1]), save=False)
    if pdf:
        version.pdf.save(f"{submission.conftool_id}.pdf", ContentFile(pdf[1]), save=False)
    version.save()
    submission.status = Submission.Status.UPLOADED if result.passed else Submission.Status.NEEDS_WORK
    submission.save(update_fields=["status"])
    Event.objects.create(submission=submission, user=user, action=f"uploaded version {number}", comment=comment)
    return version


def upload_batch(production, files, user=None, comment="", allowed=None) -> dict:
    """Add a version for every paper in the files. Returns what happened, per paper."""
    pairs, ignored = pair(files)
    papers = {s.conftool_id: s for s in (allowed if allowed is not None else production.submissions.all())}
    report = {"added": [], "failed": [], "unknown": [], "ignored": ignored}
    for number, found in sorted(pairs.items()):
        submission = papers.get(number)
        if submission is None:
            report["unknown"].append(number)
            continue
        try:
            version = add_version(submission, found.get("docx"), found.get("pdf"), user, comment)
            report["added"].append(version)
        except ValueError as error:
            report["failed"].append((number, str(error)))
    return report
