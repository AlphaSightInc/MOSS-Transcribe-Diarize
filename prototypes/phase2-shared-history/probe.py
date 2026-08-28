"""PROTOTYPE — unified Account Meeting-history policy, not production code."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from functools import cmp_to_key
from zoneinfo import ZoneInfo


NOW_MS = int(datetime(2026, 8, 28, 16, tzinfo=timezone.utc).timestamp() * 1000)
DAY_MS = 86_400_000


@dataclass(frozen=True, slots=True)
class MeetingRecord:
    meeting_id: str
    account_id: str
    mode: str
    title: str | None
    title_source: str
    status: str
    created_at_ms: int
    transcript_text: str


@dataclass(frozen=True, slots=True)
class HistoryGroup:
    key: str
    label: str
    meeting_ids: tuple[str, ...]


class DurableHistoryProbe:
    """Tiny durable model whose only mutation capability is an owner-bound handle."""

    def __init__(self, rows: tuple[MeetingRecord, ...]):
        self._rows = {row.meeting_id: row for row in rows}

    def list_owner(self, account_id: str) -> tuple[MeetingRecord, ...]:
        return tuple(row for row in self._rows.values() if row.account_id == account_id)

    def open_owner(self, account_id: str, meeting_id: str) -> "MeetingHandleProbe | None":
        row = self._rows.get(meeting_id)
        if row is None or row.account_id != account_id:
            return None
        return MeetingHandleProbe(self, account_id, meeting_id)

    def restart(self) -> "DurableHistoryProbe":
        return DurableHistoryProbe(tuple(self._rows.values()))


class MeetingHandleProbe:
    def __init__(self, store: DurableHistoryProbe, account_id: str, meeting_id: str):
        self._store = store
        self._account_id = account_id
        self.meeting_id = meeting_id

    def rename(self, title: str) -> MeetingRecord:
        normalized = title.strip()
        if not normalized:
            raise ValueError("Meeting title must not be empty.")
        row = self._store._rows[self.meeting_id]
        assert row.account_id == self._account_id
        renamed = replace(row, title=normalized, title_source="manual")
        self._store._rows[self.meeting_id] = renamed
        return renamed


def compare_history(left: MeetingRecord, right: MeetingRecord) -> int:
    left_rank = 0 if left.status == "active" else 1
    right_rank = 0 if right.status == "active" else 1
    if left_rank != right_rank:
        return left_rank - right_rank
    if left.created_at_ms != right.created_at_ms:
        return -1 if left.created_at_ms > right.created_at_ms else 1
    if left.meeting_id == right.meeting_id:
        return 0
    return -1 if left.meeting_id > right.meeting_id else 1


def day_bucket(
    created_at_ms: int,
    now_ms: int,
    local_timezone: timezone | ZoneInfo | None = None,
) -> tuple[str, str]:
    zone = local_timezone or datetime.now().astimezone().tzinfo or timezone.utc
    created = datetime.fromtimestamp(created_at_ms / 1000, tz=zone)
    now = datetime.fromtimestamp(now_ms / 1000, tz=zone)
    days = (now.date() - created.date()).days
    if days <= 0:
        return "today", "Today"
    if days == 1:
        return "yesterday", "Yesterday"
    return "earlier", "Earlier"


def history_projection(
    rows: tuple[MeetingRecord, ...],
    *,
    query: str = "",
    now_ms: int = NOW_MS,
) -> tuple[HistoryGroup, ...]:
    normalized_query = query.strip().casefold()
    matching = [
        row
        for row in rows
        if not normalized_query
        or normalized_query
        in " ".join(
            (
                row.title or "",
                row.mode,
                row.status,
                row.transcript_text,
            )
        ).casefold()
    ]
    ordered = sorted(matching, key=cmp_to_key(compare_history))
    active_ids: list[str] = []
    terminal_groups: dict[str, list[str]] = {}
    terminal_labels: dict[str, str] = {}
    for row in ordered:
        bucket, day_label = day_bucket(row.created_at_ms, now_ms)
        if row.status == "active":
            active_ids.append(row.meeting_id)
        else:
            terminal_groups.setdefault(bucket, []).append(row.meeting_id)
            terminal_labels[bucket] = day_label

    groups = [
        HistoryGroup(key="active", label="Active", meeting_ids=tuple(active_ids))
    ] if active_ids else []
    groups.extend(
        HistoryGroup(
            key=f"terminal-{bucket}",
            label=terminal_labels[bucket],
            meeting_ids=tuple(terminal_groups[bucket]),
        )
        for bucket in ("today", "yesterday", "earlier")
        if bucket in terminal_groups
    )
    return tuple(groups)


def reconcile_selection(rows: tuple[MeetingRecord, ...], selected_id: str | None) -> str | None:
    if selected_id is None:
        return None
    return selected_id if any(row.meeting_id == selected_id for row in rows) else None


def reconcile_selected_record(
    rows: tuple[MeetingRecord, ...],
    selected: MeetingRecord | None,
) -> MeetingRecord | None:
    if selected is None:
        return None
    return next((row for row in rows if row.meeting_id == selected.meeting_id), None)


def print_state(action: str, **state: object) -> None:
    print(json.dumps({"action": action, **state}, sort_keys=True))


def print_contract() -> None:
    print_state(
        "structural_contract",
        question=(
            "Can one owner workspace and owner-bound rename capability produce identical mixed-mode "
            "history across clients while search, date groups, and selection remain derived page state?"
        ),
        hypothesis=(
            "A durable Meeting summary, one total order, derived browser projection, owner-bound "
            "rename, existing Live observer, and refresh reconciliation are sufficient."
        ),
        minimum_primitives=[
            {
                "name": "durable_meeting_summary",
                "boundary": "owner workspace to restart-stable Meeting facts",
                "irreducible_because": "history and titles must survive process restart",
            },
            {
                "name": "one_total_order",
                "boundary": "active rank, created time, opaque ID tie-break",
                "irreducible_because": "separate client orders let same-Account views drift",
            },
            {
                "name": "derived_browser_projection",
                "boundary": "query, local-day groups, selected locator; never durable authority",
                "irreducible_because": "navigation state is needed but has no product ownership meaning",
            },
            {
                "name": "owner_bound_rename",
                "boundary": "MeetingHandle writes title plus manual provenance for its captured owner",
                "irreducible_because": "global rename reopens authority and missing provenance lets automation overwrite owners",
            },
            {
                "name": "existing_live_observer",
                "boundary": "selected active Live snapshot/events; no capture mutation",
                "irreducible_because": "active text changes outside durable list refresh",
            },
            {
                "name": "refresh_reconciliation",
                "boundary": "replace owner list and retain selection only when still owned/present",
                "irreducible_because": "same-Account clients otherwise retain divergent snapshots",
            },
        ],
        invariants=[
            "Live, upload, and URL-origin File Meetings share one card/group shape",
            "one newest-first Active section precedes newest-first terminal date groups",
            "search and selection grant no authority",
            "rename plus manual provenance survives restart and foreign open is a zero-mutation not-found",
            "active history observation remains read-only and never resumes capture",
        ],
        assumptions_unknowns=[
            "browser local calendar days are the intended date grouping",
            "trimmed non-empty titles are sufficient; no unmeasured maximum is invented",
            "pagination and durable cursors are unnecessary at the documented team scale",
        ],
        falsifier=(
            "Any order/group divergence, mode-specific shape, lost restart title, stale invalid "
            "selection, observer control, or foreign mutation rejects the design."
        ),
        tool_decisions=[
            {
                "experiment": "mixed_mode_projection",
                "necessary": "make global Active precedence, terminal date groups, and tie-break visible",
                "reject_if": "any terminal precedes active or a group is not newest-first",
            },
            {
                "experiment": "two_client_refresh_and_restart",
                "necessary": "separate durable truth from each client's derived snapshot",
                "reject_if": "refresh/restart does not converge order and owner title",
            },
            {
                "experiment": "owner_bound_foreign_open",
                "necessary": "exercise the mutation authority boundary",
                "reject_if": "foreign open yields a handle or changes any owner row",
            },
        ],
    )


def main() -> None:
    print_contract()
    rows = (
        MeetingRecord("active-new", "account-a", "live", None, "automatic", "active", NOW_MS - 1_000, "live now"),
        MeetingRecord("active-old", "account-a", "file", "Upload running", "automatic", "active", NOW_MS - 2 * DAY_MS, "upload"),
        MeetingRecord("terminal-tie-z", "account-a", "file", "URL review", "automatic", "completed", NOW_MS - 2_000, "url sentinel"),
        MeetingRecord("terminal-tie-a", "account-a", "file", "Upload review", "automatic", "failed", NOW_MS - 2_000, "upload failed"),
        MeetingRecord("terminal-yesterday", "account-a", "live", "Yesterday live", "automatic", "interrupted", NOW_MS - DAY_MS, "prefix"),
        MeetingRecord("foreign", "account-b", "live", "foreign sentinel", "manual", "active", NOW_MS, "foreign text"),
    )
    store = DurableHistoryProbe(rows)
    client_a = store.list_owner("account-a")
    client_a_groups = history_projection(client_a)
    print_state(
        "initial_mixed_history",
        records=[asdict(row) for row in client_a],
        groups=[asdict(group) for group in client_a_groups],
    )
    assert [group.key for group in client_a_groups] == [
        "active",
        "terminal-today",
        "terminal-yesterday",
    ]
    assert client_a_groups[0].meeting_ids == ("active-new", "active-old")
    assert client_a_groups[1].meeting_ids == ("terminal-tie-z", "terminal-tie-a")

    search_groups = history_projection(client_a, query="URL SENTINEL")
    selected = reconcile_selection(client_a, "active-new")
    print_state(
        "search_and_selection",
        query="URL SENTINEL",
        groups=[asdict(group) for group in search_groups],
        selected=selected,
        missing_selection=reconcile_selection(client_a, "foreign"),
    )
    assert search_groups[0].meeting_ids == ("terminal-tie-z",)
    assert selected == "active-new"
    assert reconcile_selection(client_a, "foreign") is None

    boundary_now = int(datetime(2026, 8, 28, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)
    boundary_created = boundary_now - 3_600_000
    utc_bucket = day_bucket(boundary_created, boundary_now, timezone.utc)[0]
    new_york_bucket = day_bucket(
        boundary_created,
        boundary_now,
        ZoneInfo("America/New_York"),
    )[0]
    print_state(
        "timezone_boundary",
        created_at_ms=boundary_created,
        now_ms=boundary_now,
        utc_bucket=utc_bucket,
        america_new_york_bucket=new_york_bucket,
    )
    assert utc_bucket == "yesterday"
    assert new_york_bucket == "today"

    client_b_before = store.list_owner("account-a")
    handle = store.open_owner("account-a", "terminal-tie-z")
    assert handle is not None
    renamed = handle.rename("  Customer URL review  ")
    client_a_after = store.list_owner("account-a")
    client_b_after_refresh = store.list_owner("account-a")
    print_state(
        "same_account_rename_convergence",
        renamed=asdict(renamed),
        second_client_before=[asdict(row) for row in client_b_before],
        first_client_after=[asdict(row) for row in client_a_after],
        second_client_after_refresh=[asdict(row) for row in client_b_after_refresh],
    )
    assert next(row for row in client_b_before if row.meeting_id == renamed.meeting_id).title == "URL review"
    assert next(row for row in client_b_after_refresh if row.meeting_id == renamed.meeting_id).title == "Customer URL review"
    assert renamed.title_source == "manual"
    repaired_selection = reconcile_selected_record(
        client_b_after_refresh,
        next(row for row in client_b_before if row.meeting_id == renamed.meeting_id),
    )
    assert repaired_selection == renamed

    restarted = store.restart()
    restarted_rows = restarted.list_owner("account-a")
    print_state(
        "restart",
        rows=[asdict(row) for row in restarted_rows],
        groups=[asdict(group) for group in history_projection(restarted_rows)],
    )
    assert next(row for row in restarted_rows if row.meeting_id == renamed.meeting_id).title == "Customer URL review"
    assert next(row for row in restarted_rows if row.meeting_id == renamed.meeting_id).title_source == "manual"

    before_foreign_attempt = restarted.list_owner("account-a")
    foreign_handle = restarted.open_owner("account-b", renamed.meeting_id)
    after_foreign_attempt = restarted.list_owner("account-a")
    print_state(
        "foreign_rename",
        outcome="not_found" if foreign_handle is None else "unexpected_handle",
        owner_rows_before=[asdict(row) for row in before_foreign_attempt],
        owner_rows_after=[asdict(row) for row in after_foreign_attempt],
        mutation_count=sum(left != right for left, right in zip(before_foreign_attempt, after_foreign_attempt)),
    )
    assert foreign_handle is None
    assert after_foreign_attempt == before_foreign_attempt
    print("VERDICT: PASS — one owner list/order and owner-bound rename converge; browser history state stays derived")


if __name__ == "__main__":
    main()
