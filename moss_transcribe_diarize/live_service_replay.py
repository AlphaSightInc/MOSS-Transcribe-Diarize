from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .app.live_service_runtime import (
    LiveServiceCreateResult,
    LiveServiceError,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceFrameResult,
    LiveServiceSnapshot,
)
from .app.live_session import AudioFrame


class ServiceReplayFailure(RuntimeError):
    exit_code = 2
    failure_kind = "integrity"


class ServiceReplayProviderConfigFailure(ServiceReplayFailure):
    exit_code = 3
    failure_kind = "provider_config"


class ServiceReplayIdentityCommitFailure(ServiceReplayFailure):
    exit_code = 4
    failure_kind = "identity_commit"


class ServiceReplayRtfFailure(ServiceReplayFailure):
    exit_code = 5
    failure_kind = "rtf"


class ServiceReplayTransportFailure(ServiceReplayFailure):
    exit_code = 6
    failure_kind = "transport_pacing"


@dataclass(frozen=True, slots=True)
class ServiceReplayOutputs:
    manifest_path: Path
    trace_path: Path
    summary_path: Path
    evaluator_path: Path


class LiveReplayService(Protocol):
    def create(self) -> LiveServiceCreateResult:
        ...

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        ...

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        ...

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        ...

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        ...

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        ...


class HttpLiveReplayService:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0):
        if not base_url:
            raise ValueError("base_url must be non-empty.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)

    def create(self) -> LiveServiceCreateResult:
        raise ServiceReplayTransportFailure("HTTP live replay service create is not implemented yet.")

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        del session_id, frame
        raise ServiceReplayTransportFailure("HTTP live replay service frame admission is not implemented yet.")

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        del session_id, since_seq
        raise ServiceReplayTransportFailure("HTTP live replay service event polling is not implemented yet.")

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        del session_id, since_version
        raise ServiceReplayTransportFailure("HTTP live replay service snapshot polling is not implemented yet.")

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        del session_id, deadline
        raise ServiceReplayTransportFailure("HTTP live replay service stop is not implemented yet.")

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        del session_id, reason
        raise ServiceReplayTransportFailure("HTTP live replay service abort is not implemented yet.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay 16 kHz mono PCM16 audio through an explicitly enabled live service runtime."
    )
    parser.add_argument("--base-url", required=True, help="Opt-in live service base URL.")
    parser.add_argument("--audio", required=True, help="16 kHz mono PCM16 WAV input.")
    parser.add_argument("--out-dir", required=True, help="Directory for replay artifacts.")
    parser.add_argument("--pace", type=float, default=1.0, help="Replay pace multiplier.")
    parser.add_argument("--max-pacing-lag", type=float, default=1.0, help="Maximum allowed pacing lag in seconds.")
    parser.add_argument("--runs", type=int, default=1, help="Number of replay runs.")
    parser.add_argument("--expect-revision", required=True, help="Expected service source revision.")
    parser.add_argument("--expect-provider-hash", required=True, help="Expected provider manifest hash.")
    parser.add_argument("--expect-config-hash", required=True, help="Expected combined configuration hash.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_service_replay(
            service=HttpLiveReplayService(base_url=args.base_url),
            audio_path=Path(args.audio),
            out_dir=Path(args.out_dir),
            pace=args.pace,
            max_pacing_lag=args.max_pacing_lag,
            runs=args.runs,
            expect_revision=args.expect_revision,
            expect_provider_hash=args.expect_provider_hash,
            expect_config_hash=args.expect_config_hash,
        )
    except ServiceReplayFailure as exc:
        print(f"live service replay failed [{exc.failure_kind}]: {exc}", file=sys.stderr)
        return exc.exit_code
    except LiveServiceError as exc:
        failure = exc.failure
        print(f"live service replay failed [{failure.kind.value}]: {failure.message}", file=sys.stderr)
        return _exit_code_for_service_failure(failure.kind)
    except Exception as exc:
        print(f"live service replay failed [integrity]: {exc}", file=sys.stderr)
        return ServiceReplayFailure.exit_code
    return 0


def run_service_replay(
    *,
    service: LiveReplayService,
    audio_path: Path,
    out_dir: Path,
    pace: float,
    max_pacing_lag: float,
    runs: int,
    expect_revision: str,
    expect_provider_hash: str,
    expect_config_hash: str,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> ServiceReplayOutputs:
    del service, audio_path, out_dir, pace, max_pacing_lag, runs
    del expect_revision, expect_provider_hash, expect_config_hash, monotonic, sleep
    raise ServiceReplayTransportFailure("service-backed paced replay runner is not implemented yet.")


def _exit_code_for_service_failure(kind: LiveServiceFailureKind) -> int:
    if kind == LiveServiceFailureKind.PROVIDER_CONFIG:
        return ServiceReplayProviderConfigFailure.exit_code
    if kind == LiveServiceFailureKind.IDENTITY_COMMIT:
        return ServiceReplayIdentityCommitFailure.exit_code
    if kind == LiveServiceFailureKind.RTF:
        return ServiceReplayRtfFailure.exit_code
    if kind == LiveServiceFailureKind.TRANSPORT_PACING:
        return ServiceReplayTransportFailure.exit_code
    return ServiceReplayFailure.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
