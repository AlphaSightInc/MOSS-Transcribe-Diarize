# Remote decoder metrics projection

| Point | running | waiting | success stop | success length | success error |
|---|---:|---:|---:|---:|---:|
| Before | 0 | 0 | 47,891 | 343 | 0 |
| After | 0 | 0 | 48,055 | 344 | 0 |

The aggregate success delta is 165 and agrees with the owned proxy's 165 starts
and 165 ends. Metrics are shared-service counters; agreement does not create
per-request content attribution.
