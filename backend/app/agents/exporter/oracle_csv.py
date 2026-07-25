"""Oracle My Inventory CSV (CLAUDE.md §3.5): pipe-delimited, dot decimal,
UTF-8 without BOM, exact column order.

Path-traversal guard (CWE-22): the ticket's own pseudocode sanitizes
`warehouse_code` down to `[a-zA-Z0-9-]` and THEN checks
`is_relative_to(BASE_EXPORT_DIR)` — but that check can never fire, because
after stripping every `.`/`/` character the filename can no longer escape
BASE_EXPORT_DIR no matter what. The ticket's own test
(`test_path_traversal_rejected`, expecting a raised ValueError for
"../../../etc/passwd") would fail against that literal pseudocode. Fixed
here by rejecting outright when sanitization changes the input, instead of
silently sanitizing and proceeding — reject-on-suspicious is safer than
silently-mutate-and-continue anyway.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.config import settings

CSV_COLUMNS = [
    "WAREHOUSE_CODE",
    "ORACLE_CODE",
    "ITEM_NAME",
    "UNIT",
    "QUANTITY",
    "COUNT_DATE",
    "SHIFT",
    "OPERATOR_ID",
    "SESSION_ID",
    "IS_VALIDATED",
    "SUPERVISOR_ID",
    "EXPORT_TIMESTAMP",
]

# Colombia has no DST — a fixed -05:00 offset is always correct.
BOGOTA_OFFSET = timezone(timedelta(hours=-5))

BASE_EXPORT_DIR = Path(settings.export_base_dir).resolve()


def get_export_path(session_id: UUID, warehouse_code: str, count_date: date, shift: str) -> Path:
    safe_warehouse = re.sub(r"[^a-zA-Z0-9\-]", "", warehouse_code)
    if safe_warehouse != warehouse_code:
        raise ValueError(f"Path traversal detectado en nombre de archivo de exportación: {warehouse_code!r}")

    filename = f"{safe_warehouse}_{count_date}_{shift}_{session_id.hex[:8]}.csv"
    export_path = (BASE_EXPORT_DIR / filename).resolve()

    if not export_path.is_relative_to(BASE_EXPORT_DIR):
        raise ValueError("Path traversal detectado en nombre de archivo de exportación")

    return export_path


def build_row(
    *,
    warehouse_code: str,
    oracle_code: str,
    item_name: str,
    unit: str,
    quantity: float | Decimal,
    count_date: date,
    shift: str,
    operator_id: str,
    session_id: UUID,
    is_validated: bool,
    supervisor_id: str | None,
    export_timestamp: datetime,
) -> dict:
    local_ts = export_timestamp.astimezone(BOGOTA_OFFSET)
    return {
        "WAREHOUSE_CODE": warehouse_code,
        "ORACLE_CODE": oracle_code,
        "ITEM_NAME": item_name,
        "UNIT": unit,
        "QUANTITY": f"{float(quantity):.4f}",
        "COUNT_DATE": count_date.isoformat(),
        "SHIFT": shift,
        "OPERATOR_ID": operator_id,
        "SESSION_ID": str(session_id),
        "IS_VALIDATED": "true" if is_validated else "false",
        "SUPERVISOR_ID": supervisor_id or "",
        "EXPORT_TIMESTAMP": local_ts.strftime("%Y-%m-%dT%H:%M:%S") + "-05:00",
    }


def generate_csv(rows: list[dict]) -> str:
    """UTF-8 without BOM is the caller's responsibility when writing to
    disk — use open(..., encoding="utf-8"), never "utf-8-sig"."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="|", lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([row[col] for col in CSV_COLUMNS])
    return buffer.getvalue()
