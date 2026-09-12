import json
import subprocess

import pytest

from moss_transcribe_diarize import phase2_acceptance_journal as journal


def record(message="started", unit="moss-web.service"):
    return {"__CURSOR": "cursor-1", "_SYSTEMD_USER_UNIT": unit, "MESSAGE": message}


@pytest.mark.parametrize("messages", [[], ["safe event"], ["out of memory", "private sentinel"]])
def test_journal_window_proves_source_and_reads_exact_tail_without_emitting_content(monkeypatch, messages):
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        rows = [record()] if "-n" in argv else [record(text) for text in messages]
        return subprocess.CompletedProcess(argv, 0, "\n".join(json.dumps(row) for row in rows), "")
    monkeypatch.setattr(journal.subprocess, "run", run)
    window = journal.ServiceJournalWindow("moss-web.service")
    assert window.observation()["read_succeeded"] is False
    assert window.read() == "\n".join(messages).encode()
    assert window.observation() == {
        "source": "systemd-user-journal", "unit": "moss-web.service",
        "baseline_cursor_observed": True, "read_succeeded": True,
        "entries": len(messages), "bytes": len("\n".join(messages).encode()),
    }
    assert calls[1][0][-2:] == ("--after-cursor", "cursor-1")
    assert "private sentinel" not in json.dumps(window.observation())


@pytest.mark.parametrize("fault", ["empty_baseline", "failed", "wrong_unit", "bad_json", "bad_message", "missing_cursor"])
def test_journal_window_rejects_unmeasured_or_unbound_source(monkeypatch, fault):
    row = record()
    if fault == "wrong_unit":
        row["_SYSTEMD_USER_UNIT"] = "unrelated.service"
    if fault == "bad_message":
        row["MESSAGE"] = None
    if fault == "missing_cursor":
        del row["__CURSOR"]
    stdout = "" if fault == "empty_baseline" else "not-json" if fault == "bad_json" else json.dumps(row)
    monkeypatch.setattr(journal.subprocess, "run", lambda argv, **kwargs:
        subprocess.CompletedProcess(argv, int(fault == "failed"), stdout, ""))
    with pytest.raises(journal.JournalMeasurementError):
        journal.ServiceJournalWindow("moss-web.service")


def test_failed_tail_does_not_inherit_success_from_baseline(monkeypatch):
    monkeypatch.setattr(journal.subprocess, "run", lambda argv, **kwargs:
        subprocess.CompletedProcess(argv, 0 if "-n" in argv else 1, json.dumps(record()), ""))
    window = journal.ServiceJournalWindow("moss-web.service")
    with pytest.raises(journal.JournalMeasurementError):
        window.read()
    assert not window.observation()["read_succeeded"]

@pytest.mark.parametrize("fault", [None, "other_unit", "other_process", "other_scope"])
def test_manager_records_are_bound_to_the_target_unit(monkeypatch, fault):
    row = record(unit="init.scope")
    row.update(USER_UNIT="moss-web.service", _COMM="systemd")
    if fault == "other_unit":
        row["USER_UNIT"] = "other.service"
    elif fault == "other_process":
        row["_COMM"] = "other"
    elif fault == "other_scope":
        row["_SYSTEMD_USER_UNIT"] = "other.scope"
    monkeypatch.setattr(journal.subprocess, "run", lambda argv, **kwargs:
        subprocess.CompletedProcess(argv, 0, json.dumps(row), ""))
    if fault:
        with pytest.raises(journal.JournalMeasurementError, match="provenance"):
            journal.ServiceJournalWindow("moss-web.service")
    else:
        window = journal.ServiceJournalWindow("moss-web.service")
        assert window.read() == b"started"
        assert window.observation()["entries"] == 1
