# Wayfinder local-markdown tracker

No issue tracker was configured, so wayfinder runs on the **local-markdown** default.

The map and its tickets live **here, in the target (product) repo**, by operator decision
(2026-08-12) — sessions run from here. The AFK control plane at
`/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize` still owns loop state,
ledgers, evidence, and review decisions.

## Layout

- `map-<nnn>-<slug>.md` — a map (label: `wayfinder:map`). The canonical artifact.
- `tickets/<ID>-<slug>.md` — child tickets of a map. `ID` is the ticket's identity.

## Ticket frontmatter

```yaml
id: T-07
map: map-001-phase1-chrome-client
title: <the ticket's name — refer to it by this, never by bare id>
type: research | prototype | grilling | task
status: open | closed
assignee: <dev driving the map, or empty>   # non-empty == claimed
blocked_by: [T-02, T-05]                    # native dependency edges
```

A ticket is **unblocked** when every id in `blocked_by` is `closed`.
The **frontier** is: `status: open` AND unblocked AND `assignee:` empty.

## Frontier query

```bash
python3 .wayfinder/frontier.py            # frontier only
python3 .wayfinder/frontier.py --all      # every ticket with state
```

## Rules that bite

- Claim before working: set `assignee` **first**, so concurrent sessions skip the ticket.
- One ticket per session (research tickets excepted).
- Resolve by appending a `## Resolution` section, setting `status: closed`, and adding a
  one-line pointer to the map's **Decisions so far**.
- The map is an index. A decision's detail lives in its ticket and nowhere else.
