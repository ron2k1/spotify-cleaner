"""Defang CSV formula injection (CWE-1236), shared by every CSV writer.

A spreadsheet treats a cell whose first character is one of these as a formula,
so a track literally named ``=HYPERLINK("http://evil","x")`` would execute when
the file is opened in Excel/Sheets. Track names, artist names and (collaborator)
playlist names are all attacker-influenceable free text, and the tool writes
them into two separate CSVs -- the scan export and the pre-delete restore
manifest. Keeping the guard in one place is deliberate: two private copies had
already drifted (the manifest writer shipped without it), so both call sites now
import this single helper and cannot fall out of sync again.
"""

from __future__ import annotations

CSV_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> str:
    """Return ``value`` as text, prefixing a quote when it leads with a risky
    character so a spreadsheet treats it as a literal string, not a formula."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in CSV_FORMULA_LEAD else s
