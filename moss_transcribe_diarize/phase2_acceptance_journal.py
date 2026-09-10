"""Read real user-service journal windows; never accept a caller-created log file."""
from __future__ import annotations

import json
import subprocess


class JournalMeasurementError(RuntimeError):
    pass


class ServiceJournalWindow:
    """A proven readable unit cursor, followed by that unit's subsequent messages."""

    def __init__(self, unit: str):
        if unit not in {"moss-web.service", "moss-vllm.service"}:
            raise JournalMeasurementError("Unsupported qualification journal unit")
        self.unit = unit
        rows = self._query("-n", "1")
        if len(rows) != 1 or not rows[0].get("__CURSOR"):
            raise JournalMeasurementError("Service journal baseline is unavailable")
        self.cursor = rows[0]["__CURSOR"]
        self.entries = self.byte_count = 0
        self.read_succeeded = False

    def _query(self, *selection):
        result = subprocess.run(
            ("journalctl", "--user", "--unit", self.unit, "--no-pager",
             "--quiet", "--output=json", *selection),
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            raise JournalMeasurementError("Service journal read failed")
        try:
            rows = [json.loads(line) for line in result.stdout.splitlines()]
        except ValueError as exc:
            raise JournalMeasurementError("Service journal returned invalid records") from exc
        if any(
            not isinstance(row, dict) or row.get("_SYSTEMD_USER_UNIT") != self.unit
            or not isinstance(row.get("MESSAGE"), str)
            for row in rows
        ):
            raise JournalMeasurementError("Service journal unit/message provenance is invalid")
        return rows

    def read(self) -> bytes:
        rows = self._query("--after-cursor", self.cursor)
        content = "\n".join(row["MESSAGE"] for row in rows).encode()
        self.entries, self.byte_count = len(rows), len(content)
        self.read_succeeded = True
        return content

    def observation(self):
        return {
            "source": "systemd-user-journal", "unit": self.unit,
            "baseline_cursor_observed": True, "read_succeeded": self.read_succeeded,
            "entries": self.entries, "bytes": self.byte_count,
        }
