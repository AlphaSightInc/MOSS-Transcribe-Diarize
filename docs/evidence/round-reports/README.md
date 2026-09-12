# Portable historical reports

Pull request (draft, unmerged, do not merge before deciding on history squash): https://github.com/aiSight-us/MOSS-Transcribe-Diarize/pull/32

Reviewed on 2026-09-12. These are historical observations, not a new qualification
or a statement of current host status. Report numbers and decisions are unchanged;
only source/link availability annotations were added. Raw bundles, screenshots,
logs, databases, credentials and audio were not copied.

Each candidate report was searched for transcript/prompt content, personal names,
cookies, credentials and token-bearing URLs, then inspected. Technical field names,
fixed UI labels, opaque session IDs, service names, paths and token-free service
origins are not transcript or credential values. Under this task's conservative
rule, reports with personal names embedded in corpus case IDs were rejected too.
A rejected copy does not establish that the original report leaked user content.

## Round 7–13 disposition

| Source | Availability / reason |
|---|---|
| `/tmp/moss-round7-stage/result/report.md` | MacStudio-local (not in repo). Rejected: name-bearing corpus case ID. |
| `/tmp/moss-round8-stage/result/report.md` | [Round 8](round-08.md). Reviewed: statuses, counters, fixed selector label and paths only. |
| `/tmp/moss-round9-stage/result/report.md` | [Round 9](round-09.md). Reviewed: scores, statuses, opaque IDs and token-free service origin; no credential values. |
| `/tmp/moss-round10-stage/result/report.md` | MacStudio-local (not in repo). Rejected: name-bearing corpus case IDs. |
| `/tmp/moss-round11-stage/result/report.md` | MacStudio-local (not in repo). Rejected: name-bearing corpus case IDs. Linked screenshots/raw records were not copied. |
| `/tmp/moss-round12-stage/result/report.md` | MacStudio-local (not in repo). Rejected: name-bearing corpus case IDs. Handback section 2 retains its existing numeric summary. |
| `/tmp/moss-round12-stage/result/quality-per-case.csv` | MacStudio-local (not in repo). Rejected: name-bearing corpus case IDs. |
| `/tmp/moss-round13-stage/result/report.md` | MacStudio-local (not in repo); absent at review. The interrupted attempt is covered by incident records below. |
| `/tmp/moss-round13-retry-stage/result/report.md` | MacStudio-local (not in repo). Rejected: name-bearing corpus case IDs. This is the completed retry, distinct from the disk-interrupted attempt. |

## Incident, recovery and supporting records

| Source | Availability / reason |
|---|---|
| `/tmp/moss-host-recovery/incident-status.md` | [Incident timeline](host-incident-status-20260912.md). Reviewed status chronology; later entries supersede earlier ones. |
| `/tmp/moss-host-recovery/sparse-result.md` | [Sparse attempt](host-sparse-result-20260912.md). Reviewed sizes, process IDs, statuses and paths. Its failed sparse attempt predates the successful move. |
| `/tmp/moss-host-recovery/recovery-report.md` | MacStudio-local (not in repo). Rejected: personal profile identifier in a Windows path. No edited/redacted substitute is presented as the original. |
| `/tmp/moss-draft-headroom-20260911/REPORT.md` | [Draft headroom](draft-headroom-20260911.md). Reviewed numeric measurements and statuses. Original recommendation is preserved; the handback records the later operator decision. |
| Local-stack `scratchpad/localstack/NOTES.md` cited in the handback | MacStudio-local (not in repo). Rejected: name-bearing corpus case ID. |

Remaining `/tmp` artifact citations in the audits/handoffs are explicitly marked
**MacStudio-local (not in repo)**. They are raw or mixed-content artifacts,
unreviewed companion files, scratch environments, or unavailable historical files;
no recursive copying or assumption of safety was made. Command examples retain
working syntax: their scratch destinations are not links to retained evidence.

Copied reports' companion links are converted to labelled local paths unless the
companion was separately reviewed and copied. The handback's audit index uses only
repository-relative links. No product, test, build, bound or policy file changed;
no host operation was performed.

## Round 14 — sanitized copy

[Round 14](round-14.md) preserves all numbers and verdicts. Name-bearing corpus IDs were replaced with consistent neutral case numbers, explicitly labelled as sanitization; the original report remains MacStudio-local. Reviewed remaining prose, tables and JSON: statuses, measurements, opaque session IDs, technical paths and token-free service origins only. No transcript/prompt text, audio, screenshots or credential values copied. Companion links are annotated local paths.

## Round 15 — sanitized copy

[Round 15](round-15.md) preserves numbers and verdicts. Corpus IDs replaced with neutral case numbers; remaining fields reviewed as statuses, metrics, opaque identifiers, technical paths and token-free origins. No transcript/prompt text, credentials, audio or screenshots copied. Companion artifacts remain explicitly MacStudio-local.
