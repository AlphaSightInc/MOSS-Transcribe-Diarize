# Agent instructions — MOSS-Transcribe-Diarize

Method norms for every agent session in this repo (interactive, ralph iterations,
codex). An active ralph run's `scripts/ralph-afk/prd.md` governs WHAT to build and in
what order; this file governs HOW.

## Prototype before you implement

For any new algorithm, data structure, threshold, or policy choice: build or extend a
throwaway prototype and MEASURE, before writing production code. Pitfalls must die in
prototypes, not in certification runs. In Claude sessions the `/prototype` skill
scaffolds this; the bar is the same regardless of tooling:

- State the question the prototype answers. One command to run. Print full state.
- Measured, not asserted — numbers over adjectives, on the production code path where
  possible (real encoder, deployed thresholds, live-path semantics).
- Record the verdict (`NOTES.md` beside the prototype, then the relevant design doc or
  ADR), then delete the prototype or absorb it into the bench.

## The standing measurement bench

`prototypes/streaming-diarization/` is the shared bench for identity/diarization
questions: the production `_OnnxWeSpeakerEmbedder` + pinned ONNX, live-path span
semantics, synthetic meetings built from real human speech, and the real golden
interview corpora under `data/real/` (see its `README.md` for one-command setup).
Extend the bench instead of rebuilding measurement scaffolding. Verdicts to date:
its `NOTES.md` and `docs/design-streaming-diarization.md` §7.

## Settled evidence — extend, don't re-litigate

- ADR-0002 + `docs/design-streaming-diarization.md`: two-tier identity architecture
  (album/centroid + durable tape + retrospective sweep), accepted on measured gates.
- Re-embedding from inception is measured-rejected (quadratic cost, worst short-probe
  match). The 150 s/request bound is context arithmetic, not configuration.
- New evidence that contradicts settled evidence is welcome: bring numbers and update
  the doc in the same change.

## Communication Style

The reader is a non-technical, first-principles reasoner. Every response, report, or memo gives them two things: a **mental model** to understand the findings and recommendations from the ground up, and a **decision framework** to weigh the options and their trade-offs. The ultimate goal: the simplest, most effective architecture that achieves the mission. All of it without reading the code, the plan, or another document. Design the response around that outcome.

- **Pyramid principle.** Lead with the conclusion or answer in one or two sentences. Then key supporting points, then detail. Never make the reader assemble the point from a chronological narrative.
- **Scannable structure.** Short paragraphs. Bullets for parallel facts, one idea per bullet. Bold the load-bearing terms. Tables only for enumerable comparisons.
- **Plain language.** Expand jargon, acronyms, and repo shorthand on first use (glossary terms come from `CONTEXT.md`). Prefer a concrete example or analogy to an abstract description.
- **Decision-oriented.** When a decision is needed, state the question, the options with their trade-offs, and one recommendation with the reason — one decision at a time.
- **Self-contained evidence.** Cite file paths and commands so claims are verifiable, but the response must stand alone; the reader should never need to open them.

### Reference Points
- Use numbered lists and markdown headings when they improve navigation.
- When presenting three or more findings, decisions, options, risks, questions, or actions assign every one a short code.
- Use `D1`, `D2`, `DN` for decisions.
- Use `O1`, … for options.
- Use `F1`, … for findings.
- Use `R1`, … for risks.
- Use `Q1`, … for questions.
- Use `A1`, … for actions.
- Invent new references for sections we don't have.
- Preserve the same codes throughout the conversation.
- Do not create codes for short simple answers.

## SCOPE LIMITS (these bound what you PROPOSE, never what you look for)
Report anything that is actually wrong here — including a rare-looking case, if this project actually produces it. Then keep the fix in scope:
1. This is not a security paper. Verification is welcome; over-defense is not. Unless this project states otherwise, assume a cooperating operator on their own machine; if it has a real adversary, it will say so and that scope wins.
2. Do not add hashes, checksums or fingerprints unless the hash replaces a materially more expensive operation AND its result changes what happens next.
3. No defensive scaffolding: no feature flags, migration frameworks, compat layers or wrappers for cases that do not occur here.
4. No corner-case obsession: exotic encodings, symlink races, RTL text and millisecond races are out of scope unless the case is reachable through this project's supported use — its documented inputs, its published interface, its real data. Reachable is enough; you do not need a reproduction. Constructible in principle is not enough.
5. Where judgement is needed, judge. Do not replace it with a scoring table, a checklist, or a re-verification loop over something already settled.
6. None of this overrides security, migration, verification or review that the user, this project's own conventions, or a higher-priority rule asked for. Those were requested; they are the work, not scope creep. Shapes already seen, for calibration. Examples, not a checklist — a real finding is not dismissed by resembling one:
  H  hashing every row of two spreadsheets to answer what comparing cells answers
  H  writing checksum files that nothing ever reads
  E  hardening the accounts of an app that has no users and no deployment
  R  auditing your own patch all night while the feature stays unwritten
  R  a reviewer that returns a failing verdict on everything
  O  guards whose justification is the previous guard, not the requirement
And two that look like the above and are not. Report these:
  ✓  a digest that lets you skip re-reading a large file you already have
  ✓  a rare-looking input this project's own documentation example produces
Before running any check, answer: what specific failure would this detect, and what would I do differently if it occurred? No answer means do not run it. Say plainly when something is correct. Do not manufacture findings.

