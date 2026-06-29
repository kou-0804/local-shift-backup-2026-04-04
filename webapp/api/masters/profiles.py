"""Byte-fidelity descriptors + the byte-exact CSV serializer core.

Production runs on Windows, where text-mode writes translate ``\\n`` -> ``\\r\\n``.
We therefore capture each file's *measured* byte profile (BOM? newline? trailing
newline?) at import time and reproduce bytes by hand: stdlib ``csv`` for quoting
fidelity, then explicit newline/BOM/trailing control, written in binary mode.
NEVER use pandas in this path (it re-encodes and re-normalizes newlines).
"""
import csv
import io
import os
from dataclasses import dataclass, field
from typing import List

BOM = b"\xef\xbb\xbf"


@dataclass
class FileProfile:
    logical_name: str
    filename: str
    has_bom: bool
    newline: str            # "\n" or "\r\n"
    trailing_newline: bool
    header_text: str        # exact first physical line (decoded, sans BOM, sans newline)
    format_json: dict = field(default_factory=dict)  # per-file structural extras


def capture_profile(path, *, logical_name="", format_json=None) -> FileProfile:
    """Read the *real* bytes and record BOM / newline / trailing-newline truth.

    Do not trust loader encoding labels (several say utf-8-sig but only 予定申請
    actually carries a BOM). The on-disk bytes are the only source of truth.
    """
    raw = open(path, "rb").read()
    has_bom = raw.startswith(BOM)
    body = raw[len(BOM):] if has_bom else raw
    newline = "\r\n" if b"\r\n" in body else "\n"
    trailing_newline = body.endswith(b"\n")
    first = body.split(b"\n", 1)[0].decode("utf-8").rstrip("\r")
    return FileProfile(logical_name, os.path.basename(path), has_bom, newline,
                       trailing_newline, first, format_json or {})


def write_bytes(rows: List[List[str]], profile: FileProfile) -> bytes:
    """rows: list[list[str]] -> exact CSV bytes per the profile.

    Hand-serialized: stdlib csv for quoting fidelity (QUOTE_MINIMAL reproduces
    業務拡大 trainee quoting and pad-comma empty fields), then explicit
    newline/BOM/trailing control. The two no-trailing-newline files are handled
    by stripping the final terminator.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator=profile.newline, quoting=csv.QUOTE_MINIMAL)
    for r in rows:
        w.writerow(r)
    text = buf.getvalue()
    if not profile.trailing_newline and text.endswith(profile.newline):
        text = text[: -len(profile.newline)]
    data = text.encode("utf-8")
    return (BOM + data) if profile.has_bom else data
