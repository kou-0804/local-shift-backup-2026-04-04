"""Confirm a roster into an immutable, checksummed monthly archive.

``confirm_roster`` renders the Direction-A Excel via the single-source
``roster_render.render_roster_excel`` (deterministic -> stable checksum), stores
the bytes + SHA-256 in ``archives`` (replacing any prior archive for the same
roster on re-confirm), and flips ``rosters.status`` to 'confirmed'.
"""
import hashlib
from datetime import datetime, timezone

from webapp.api.roster_render import render_roster_excel


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def confirm_roster(conn, rid: int, user_id: str = "") -> dict:
    xlsx, d = render_roster_excel(conn, rid)
    checksum = hashlib.sha256(xlsx).hexdigest()
    archived_at = _now_iso()
    year, month = d["year"], d["month"]
    # Re-confirm replaces the prior snapshot so the deterministic checksum holds.
    conn.execute("DELETE FROM archives WHERE roster_id=?", (rid,))
    conn.execute(
        "INSERT INTO archives(roster_id, year, month, xlsx_bytes, checksum, "
        "archived_at, archived_by) VALUES(?,?,?,?,?,?,?)",
        (rid, year, month, xlsx, checksum, archived_at, user_id or None),
    )
    conn.execute(
        "UPDATE rosters SET status='confirmed', confirmed_at=? WHERE id=?",
        (archived_at, rid),
    )
    conn.commit()
    return {"roster_id": rid, "year": year, "month": month,
            "checksum": checksum, "archived_at": archived_at}


def list_archives(conn) -> list:
    """Public list (no BLOB) of confirmed-month archives, newest month first."""
    rows = conn.execute(
        "SELECT id, roster_id, year, month, checksum, archived_at, archived_by "
        "FROM archives ORDER BY year DESC, month DESC, id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_archive_bytes(conn, archive_id: int):
    """Return ``(xlsx_bytes, year, month)`` or ``None`` if no such archive."""
    row = conn.execute(
        "SELECT xlsx_bytes, year, month FROM archives WHERE id=?", (archive_id,)
    ).fetchone()
    if row is None:
        return None
    return row["xlsx_bytes"], row["year"], row["month"]
