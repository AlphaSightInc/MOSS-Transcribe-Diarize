from __future__ import annotations

from .app.live_provider_bundle import main as _bundle_main


def main(argv: list[str] | None = None) -> int:
    """Run read-only live bundle preflight with --manifest and optional --json."""
    return _bundle_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
