# G4 recovery and deployed 10/10 rebaseline — 2026-08-25

## Verdict

**G1-G7 PASS.** The overlap refusal is closed without weakening session validation or advancing
canonical authority without published text. Across 12 actual-live sessions and 1,239.987 paced
audio-seconds, all **122/122** full 10-second windows applied in order; refusals, evictions,
failed/stale windows, admission refusals, and terminal failures were all zero.

The new settled pre-Stop 10/10 baseline is macro WER **.140442**. It is the frozen Goal-1 control.
Do not start 15/10 production work until the owner signs `D-M2-3.md` as O2 with a correction-p95
ceiling.

## 1. Defect before and after

| Evidence | Before | After |
|---|---:|---:|
| Jamie rolling authority | stopped near 40 s | full 180 s, both passes |
| Jamie window 4 | `segments_out_of_order` | applied, 2,720 samples displaced |
| Jamie completed/applied grid | refusal after four accepted windows; later `pcm_evicted` | windows 0-17 applied |
| Jamie words lost by normalization | unmeasured proposal rejected whole | 0/24 lost; merge/drop 0 |
| Jamie settled WER | .118467 | .094077 |
| six-case settled macro WER | .144507 | .140442 |

The repair is one producer-neutral overlap resolver used before both rolling and terminal
publication. A still-invalid rolling proposal now becomes explicit `proposal_refused`, records
its stable reason, releases retained PCM, leaves transcript/frontier bytes and values unchanged,
and lets base capture continue with exact accounting. It does not skip the canonical pointer.

Prototype denominator: 122 retained proposals from two six-case passes. Ordinary proposals were
byte-identical `120/120`; normalized proposals applied `122/122`; no word or gated score regressed.
Cached production-class Jamie replay applied windows 0-4 and queued window 5.

## 2. Exact G4 gates

| Gate | Result | Evidence |
|---|---|---|
| G1 exact execution | PASS | 12 sessions; 1,239.987 s; exact samples; raw events, snapshots, traces, and four surfaces retained |
| G2 rolling coverage | PASS | 122/122 ordered windows applied: `5,6,6,18,18,8` per pass |
| G3 cause closure | PASS | all refusal/eviction/failure/stale/admission/terminal counts zero |
| G4 Jamie witness | PASS | both live passes completed 0-17; each displaced 2,720 samples, dropped/merged zero |
| G5 runtime | PASS | combined pre-Stop RTF `.157340`; worst session `.168776`; queue max 1; endpoint drained 0/0 |
| G6 surfaces | PASS | six quality and four latency measures below; full per-case/category/weighted record in `G4-GATES.json` |
| G7 provenance | PASS | descriptor/model/corpus hashes stable; patch and file hashes fixed across restart/campaign |

One non-controlling diagnostic failed: Javier Pass A's legacy per-request canonical-decoder p95
RTF was `3.27197`. G5 governs **combined** pre-Stop inference RTF, which passed for every session
and overall. The raw stress result is retained, not substituted or hidden.

## 3. New deployed 10/10 quality baseline

Two-pass means; settled is the future pre-Stop control.

| Case | Immediate WER | Settled WER | Recall | TBSA | DER | Matched speaker acc. | Ref-speech DER | Final WER |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Javier 50 s | .194690 | .159292 | .867257 | .875427 | .113000 | .867257 | .093316 | .097345 |
| Bill 60 s | .267045 | .204545 | .920455 | .875387 | .128250 | .914773 | .112836 | .159091 |
| Keyu 60 s | .143885 | .115108 | .978417 | .891296 | .111167 | .978417 | .090519 | .064748 |
| Adam 180 s | .146893 | .133710 | .941620 | .899841 | .091167 | .941620 | .077717 | .126177 |
| Jamie 180 s | .111498 | .094077 | .947735 | .919246 | .094352 | .932056 | .081653 | .069686 |
| RTFL 89.9935 s | .135922 | .135922 | .922330 | .800622 | .430644 | .834951 | .352785 | .053398 |
| **Macro** | **.166655** | **.140442** | **.929636** | **.876970** | **.161430** | **.911512** | **.134804** | **.095074** |
| **Duration-weighted** | **.150216** | **.129643** | **.936111** | **.885911** | **.148653** | **.918326** | **.124682** | **.094127** |

Settled category means:

| Category | WER | Recall | TBSA | DER | Matched speaker acc. | Ref-speech DER |
|---|---:|---:|---:|---:|---:|---:|
| monologue | .159292 | .867257 | .875427 | .113000 | .867257 | .093316 |
| two-person interview | .151121 | .946831 | .888841 | .110195 | .944937 | .093691 |
| multi-person discussion | .094077 | .947735 | .919246 | .094352 | .932056 | .081653 |
| multi-person conversation | .135922 | .922330 | .800622 | .430644 | .834951 | .352785 |

## 4. Separate latency clocks

Nearest-rank p95 for first publication and changed-region correction; two-pass mean for drain and
Stop-to-final.

| Case | First publication p95 s | Correction p95 s | Drain mean s | Stop-to-final mean s |
|---|---:|---:|---:|---:|
| Javier | 3.312656 | 10.845014 | .675795 | 2.163179 |
| Bill | 3.348384 | 8.090386 | .841517 | 3.041683 |
| Keyu | 3.330360 | 8.037756 | .665749 | 1.972533 |
| Adam | 3.537279 | 10.527801 | .338934 | 7.766455 |
| Jamie | 3.734393 | 10.474767 | .850296 | 9.097724 |
| RTFL | 3.489595 | 8.781206 | .000388 | 3.820041 |
| **Macro mean** | **3.458778** | **9.459488** | **.562113** | **4.643603** |
| **Duration-weighted mean** | **3.531165** | **9.807608** | **.545686** | **6.110295** |

Pooled distributions are first publication **3.652696 s p95** over 536 regions, correction
**10.471099 s p95** over 494 changed regions, drain **.910279 s p95**, and Stop-to-final
**9.118021 s p95**. Pass A/B correction p95 differs by only `.001508 s`; first-publication p95
differs by `.020804 s`.

These clocks answer different questions. First publication is provisional availability;
correction is how long a changed region waits for rolling ownership; drain is the wait before
Stop; Stop-to-final is terminal replacement after capture. Shadow word availability and browser
paint were not measured in this actual-only run.

## 5. Historical shadows are not a comparator

The prior sweep reported deployed 10/10 macro WER `.1445`, 15/10 lexical shadow `.1084`, and
15/10 stable-anchor shadow `.1059`. Those shadows ran off-path and covered Jamie audio that the old
deployed control lost. They remain research context only. A promotion delta requires fresh
deployed ABBA control/candidate sessions after an O2 owner ruling.

## 6. Provenance and reproduction

- Branch/HEAD: `ralph/live-convergence-0824` /
  `7608c91ce36441d9075fbba41e18c5fae8f464ac`.
- Production patch SHA-256:
  `b006de9b04c73315c4c6e323d77fe112739fcd33f0d0110e13794133a5278e85`.
- Results SHA-256:
  `ed9813f4009e869f27f4b6171223153a80e9837f361681de0ca11c5c9396e44d`.
- Gate artifact SHA-256:
  `084945d57538e248f0b213e0c74b55b2018740190f50bb2901b602bdf57fd97d`.
- Corpus manifest SHA-256:
  `80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c`.
- Service after campaign: PID `57283`, listener `*:7861`, model queue `0/0`.

Campaign command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/moss_sweep.py \
  --corpus evidence/live-policy-sweep-20260825/corpus \
  --output evidence/live-g4-recovery-20260825/deployed-10-10 \
  --passes 2 --actual-only
```

Validation passed in layers: focused `86 passed, 19 subtests`; replay `29 passed, 9 subtests`;
full repository `1160 passed, 2 skipped, 411 subtests`; cached Jamie verifier PASS.

Raw controlling artifacts: `G4-GATES.json`, `deployed-10-10/moss-results.json`,
`normalization-prototype.json`, `jamie-production-class-probe.json`, `production.patch`,
`restart-{pre,post}.json`, and `campaign-post.json` in this evidence root.

## 7. Next authorized action

Owner signs `D-M2-3.md` as **O1** or **O2**. Goal 2 remains prohibited until signed O2 includes
an explicit maximum correction p95.
