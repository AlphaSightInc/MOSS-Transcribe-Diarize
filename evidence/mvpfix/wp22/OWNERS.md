# WP22 measured owner bytes

Recursive Python ownership estimates; not additive physical RAM. Album count means speaker banks.

## mono-base

| Owner | bytes at 5 min | 15 min | 30 min | post-Stop bytes / count |
|---|---:|---:|---:|---:|
| mixer_frames | 33000 | 33000 | 33000 | 40 / 0 |
| replay_acks | 90050 | 90050 | 90050 | 90050 / 256 |
| tape_mixed | 10350062 | 10350062 | 10350062 | 56 / 0 |
| pending_pcm_mixed | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_analysis | 65256 | 65256 | 65256 | 760 / 0 |
| session_frames | 1236 | 1236 | 1236 | 760 / 0 |
| commits | 39295 | 120583 | 248263 | 248612 / 720 |
| spans | 224 | 224 | 224 | 224 / 0 |
| revisions | 22724 | 69524 | 139724 | 140504 / 720 |
| events | 483319 | 487607 | 488135 | 493804 / 1000 |
| canonical_timing | 224 | 224 | 224 | 224 / 0 |
| rolling_timing | 224 | 224 | 224 | 224 / 0 |
| rolling_buffer | 306062 | 306062 | 306062 | 56 / 0 |
| pending_vectors_mono | 69176 | 69176 | 69176 | 60608 / 7 |
| album_mono | 167567 | 251095 | 251095 | 251095 / 3 |
| sweep_mono | 186125 | 565849 | 1133139 | 1134721 / 720 |

## lanes-before

| Owner | bytes at 5 min | 15 min | 30 min | post-Stop bytes / count |
|---|---:|---:|---:|---:|
| mixer_frames | 33000 | 33000 | 33000 | 40 / 0 |
| replay_acks | 90050 | 90050 | 90050 | 90050 / 256 |
| tape_mixed | 10350062 | 10350062 | 10350062 | 56 / 0 |
| tape_system | 10350062 | 10350062 | 10350062 | 56 / 0 |
| tape_microphone | 10350062 | 10350062 | 10350062 | 56 / 0 |
| pending_pcm_mixed | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_analysis | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_system | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_microphone | 65256 | 65256 | 65256 | 760 / 0 |
| session_frames | 1236 | 1236 | 1236 | 760 / 0 |
| commits | 50726 | 155598 | 318318 | 318762 / 720 |
| spans | 224 | 224 | 224 | 224 / 0 |
| revisions | 47429 | 49053 | 49053 | 49053 / 240 |
| events | 479936 | 465145 | 465145 | 468046 / 1000 |
| canonical_timing | 224 | 224 | 224 | 224 / 0 |
| rolling_timing | 224 | 224 | 224 | 224 / 0 |
| rolling_buffer | 306062 | 56 | 56 | 56 / 0 |
| pending_vectors_system | 224 | 224 | 224 | 224 / 0 |
| album_system | 125694 | 167458 | 167458 | 167458 / 2 |
| sweep_system | 186758 | 567782 | 1137022 | 1138552 / 720 |
| pending_vectors_microphone | 224 | 224 | 224 | 224 / 0 |
| album_microphone | 167458 | 167458 | 167458 | 167458 / 2 |
| sweep_microphone | 186509 | 567003 | 1135448 | 1136978 / 720 |

## lanes-after

| Owner | bytes at 5 min | 15 min | 30 min | post-Stop bytes / count |
|---|---:|---:|---:|---:|
| mixer_frames | 33000 | 33000 | 33000 | 40 / 0 |
| replay_acks | 90050 | 90050 | 90050 | 90050 / 256 |
| tape_mixed | 10350062 | 10350062 | 10350062 | 56 / 0 |
| tape_system | 10350062 | 10350062 | 10350062 | 56 / 0 |
| tape_microphone | 10350062 | 10350062 | 10350062 | 56 / 0 |
| pending_pcm_mixed | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_analysis | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_system | 65256 | 65256 | 65256 | 760 / 0 |
| pending_pcm_microphone | 65256 | 65256 | 65256 | 760 / 0 |
| session_frames | 1236 | 1236 | 1236 | 760 / 0 |
| commits | 50726 | 155598 | 318318 | 318762 / 720 |
| spans | 224 | 224 | 224 | 224 / 0 |
| revisions | 47429 | 49053 | 49053 | 49053 / 240 |
| events | 479936 | 465145 | 465145 | 468046 / 1000 |
| canonical_timing | 224 | 224 | 224 | 224 / 0 |
| rolling_timing | 224 | 224 | 224 | 224 / 0 |
| rolling_buffer | 306062 | 56 | 56 | 56 / 0 |
| pending_vectors_system | 224 | 224 | 224 | 224 / 0 |
| album_system | 125694 | 167458 | 167458 | 167458 / 2 |
| sweep_system | 186758 | 567782 | 1137022 | 1138552 / 720 |
| pending_vectors_microphone | 224 | 224 | 224 | 224 / 0 |
| album_microphone | 167458 | 167458 | 167458 | 167458 / 2 |
| sweep_microphone | 186509 | 567003 | 1135448 | 1136978 / 720 |

Exact exemplar counts from the byte-identical cached replay (content and bank counts checked against uncached):

| Audio seconds | System entries | Mic entries |
|---|---:|---:|
| 300 | 15 | 20 |
| 900 | 20 | 20 |
| 1800 | 20 | 20 |
