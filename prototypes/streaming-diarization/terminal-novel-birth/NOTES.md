# Terminal-only novel-person birth

**THROWAWAY PROTOTYPE — no production change without root review.**

## Contract

- **Structural question:** when the terminal decoder emits a local voice absent from the settled
  live album, can the existing unchanged match/birth/admission policy safely create a new durable
  person instead of requiring every terminal voice to have existed live?
- **Minimum primitives:** terminal local-speaker evidence unit; settled known-person album;
  unchanged score/margin matcher; independent 1.0 s birth floor; 2.0 s album admission floor;
  durable owner of the next canonical ID. Remove the unit and there is no voice evidence; remove
  the album and returning people cannot falsify birth; remove either floor and the tested policy
  changes; remove ownership and a proposed ID cannot reach publication safely.
- **Invariants:** no threshold changes; real encoder and retained terminal intervals only; each
  probe starts from the same known album; an ambiguous match abstains rather than births; an
  already-known short utterance must not mint a duplicate; source words/times never change.
- **Assumptions/unknowns:** the 165.69–166.88 terminal segment carries the source words attributed
  to Jamie, but the human reference boundary is coarser (165.60–169.43) and may contain silence,
  laughter, or another boundary effect. The prototype therefore calls it the *terminal novel
  candidate* and does not establish the person's name from the coarse row alone.
- **Falsifier:** reject if any source-known Ben/David probe of at least 1.0 s would birth a
  duplicate; if the terminal candidate is ambiguous rather than cleanly unmatched; or if its
  birth cannot produce the existing album's named `PROVISIONAL`/`ADMITTED` disposition.
- **Tool decision:** one offline production-encoder batch over retained source intervals, followed
  by the production matcher and album classes. No decoder, service, network, or GPU lease.

## Retained evidence

Known-album exemplars and short controls are exact spans from the already-retained 30–180 s
terminal decode, source-adjudicated against `discussion_jamie_dimon_180s/reference.jsonl`:

- album: three David spans at 120.64–135.42 s; six Ben spans at 135.78–162.16 s;
- false-birth controls: Ben 163.52–164.52 and 178.97–180.00; David 169.47–170.84 and
  174.87–176.22;
- novel candidate: terminal S03 165.69–166.88, plus trims wholly inside that decoder span;
- boundary diagnostics only: left/right/coarse slices inside reference 165.60–169.43 and the
  adjacent live `laughing` interval 167.08–168.93. These do not name the voice.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/terminal-novel-birth/probe.py
```

## Result

**SUPPORTED, narrowly.** On this retained source slice, the unchanged production policy can
represent a terminal-only novel person without assuming that every final voice existed live.

- The four distinct known-person controls (Ben 1.00/1.03 s; David 1.35/1.37 s) all matched the
  correct existing person. False births: **0/4**.
- The exact 1.19 s terminal candidate scored 0.077 to Ben and 0.009 to David, so it took the
  existing birth path. Because it is shorter than the unchanged 2.0 s admission floor, the album
  returned **`provisional`**, not an admitted durable identity.
- Both 1.09 s trims wholly inside the terminal span also produced the same provisional birth.
  Their cosines to the exact vector were 0.965 and 0.984.
- The coarse 3.83 s reference interval also birthed and was admitted, but it is not valid identity
  proof: it crosses the adjacent laughter region and its vector cosine to the exact terminal span
  fell to 0.880. The right-edge and laughter diagnostics had 0.000 production cosine to the exact
  candidate.

This establishes a reachable policy outcome, not the candidate's human name and not a population
false-birth rate. The source timing and terminal text make the candidate consistent with the Jamie
turn, but the coarse reference row alone cannot adjudicate the 1.19 s voice identity.

Full machine-readable evidence is in `results.json`.

## Smallest ownership handshake for root review

The missing primitive is not another identity algorithm. It is one owner-mediated terminal birth
transaction:

1. The terminal decoder proposes one local-speaker evidence unit with its retained source-time
   intervals and vector.
2. The existing live identity owner scores it against the settled album and applies the unchanged
   ambiguity, 1.0 s birth, capacity, and 2.0 s admission rules.
3. If birth is allowed, that owner allocates the next canonical ID, observes the vector in its
   album as `provisional` or `admitted`, and publishes the updated identity snapshot.
4. Only then may the terminal segment reference that canonical ID. Failure or deferral remains
   explicit unknown.

Do not let `revision_reader()` or the finalizer mint an ID independently. The reader lacks the
owner's mutable album/birth-deferral state, while the current lane conversion projects proposed
new IDs through the older base speaker list and therefore turns them back into `None`. Commit of
identity state and use of the new ID must be one ownership operation so transcript and album cannot
disagree.

No production change was made pending root review.
