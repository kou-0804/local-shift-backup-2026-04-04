"""P4c: confirm-lock + monthly archive.

Confirming a roster (admin only) flips its status draft->confirmed and stores
the rendered Direction-A Excel bytes + a SHA-256 checksum in the ``archives``
table. Viewers list/download confirmed months; they never see drafts.
"""
