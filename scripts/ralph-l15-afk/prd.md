# Campaign L1.5 execution contract

**Ralph contract:** `moss-l15-live-uplift-v1`

Authority is prototype-only Campaign L1.5, maximum twelve iterations. The
controlling plan is `docs/plans/l15-live-uplift-0804.md`, SHA-256
`456cb01efc7e9ffbfeb1091f251f03a666ee81d3ff2ca9229faaf93faab8cdce`.

No product code, product tests, deployment, service, host, manifest, push, or
keeper merge is authorized. Raw measurements and SHA-256 manifests are required.
Any predeclared gate failure records BLOCKED and ends the campaign.

The promoted corpus is pinned now. The split pin remains `UNFROZEN` through L0;
gated work must refuse until L1.a commits the split, opening-once procedure, and
real split SHA-256 pin atomically.
