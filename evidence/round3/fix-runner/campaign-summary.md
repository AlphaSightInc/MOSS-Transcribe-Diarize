# Literal S7 and S8 result

Command population: two 300-second Live sessions (`mono_javier_intro_50s`,
`discussion_jamie_dimon_180s`), one 150-second File and one 150-second URL at
t=60 seconds, then paired Stop and one 150-second File. Verdict: **PASS / clean**.

| S7 Live lane | p95 canonical lag | first/last-third median | accepted/accounted | retry/wrong owner |
|---|---:|---:|---:|---:|
| mono Javier | 2.819 s | 1.187 / 1.309 s | 4,800,000 / 4,800,000 | 0 / 0 |
| Jamie Dimon discussion | 2.432 s | 1.150 / 1.639 s | 4,800,000 / 4,800,000 | 0 / 0 |

Both p95 values are below 10 seconds. First-to-last-third median growth is 0.123
and 0.489 seconds respectively: no accumulating backlog. Mixed File/URL completed
with 29 segments each.

| Background owner | windows | acceptance to first dispatch | wait p50 / p95 / max | interleaved |
|---|---:|---:|---:|---:|
| S7 File | 2/2 | 4.313 s | 2.442 / 4.049 / 4.049 s | yes |
| S7 URL | 2/2 | 0.243 s | 1.948 / 3.896 / 3.896 s | yes |
| S8 File | 2/2 | 0.182 s | 4.858 / 9.715 / 9.715 s | yes |
| terminal lane A | 3/3 | n/a | 4.729 / 5.514 / 5.514 s | contended |
| terminal lane B | 3/3 | n/a | 6.326 / 8.779 / 8.779 s | contended |

Every one of 342 windows retains owner, index, accepted, wait-started, started,
and ended clocks in `s7-s8-2x300/result.json`. Denominator is 342/342 complete;
maximum total/background in-flight is 2/1; Live preemption is 10/10. Terminal
contention is separately measured at 22.604 seconds.

S8 paired-Stop gap was 0.000058 seconds; File submission began 0.0285 seconds
after the last Stop request. Its first dispatch was 0.182 seconds, before either
31.120-second Stop-to-final interval completed, and its two windows fairly yielded.

Request receipt: 342/400 started and 342 finished; maximum proxy active 2; no
foreign load or failures. Tunnel 18271 and stack/media 17990/17991 closed; lease FREE.
