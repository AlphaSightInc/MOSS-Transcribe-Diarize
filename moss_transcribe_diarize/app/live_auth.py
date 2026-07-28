from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


PAIRING_TTL_SECONDS = 300
VIEW_ABSOLUTE_CAP_SECONDS = 12 * 60 * 60
PAIRING_PAYLOAD_PREFIX = "mtd1"
SECRET_BYTES = 32

CAPTURE_ACTIONS = frozenset({"create", "frame", "heartbeat", "snapshot", "events", "stop", "abort"})
VIEW_ACTIONS = frozenset({"snapshot", "events", "stop", "abort"})

# View authority lives exactly as long as the session it was bound to is still running.
# The allowlist fails closed: any status the lifecycle owner adds later revokes the view
# until it is admitted here deliberately.
VIEWABLE_SESSION_STATUSES = frozenset({"active", "closing"})

_ALLOWED_PEER_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "fc00::/7",
        "fe80::/10",
    )
)


class LiveAccessError(Exception):
    status_code = 403


class LiveAccessUnauthorized(LiveAccessError):
    status_code = 401


class LiveAccessForbidden(LiveAccessError):
    status_code = 403


class LiveAccessConflict(LiveAccessError):
    status_code = 409


@dataclass(frozen=True, slots=True)
class LivePeer:
    host: str
    scheme: str

    @property
    def address(self) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        return ipaddress.ip_address(self.host)

    @property
    def is_loopback(self) -> bool:
        return self.address.is_loopback


@dataclass(frozen=True, slots=True)
class PairingGrant:
    pairing_payload: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class CapturePrincipal:
    device_id: str


@dataclass(frozen=True, slots=True)
class ViewPrincipal:
    session_id: str


@dataclass(frozen=True, slots=True)
class DescriptorPrincipal:
    pass


LivePrincipal = CapturePrincipal | ViewPrincipal | DescriptorPrincipal


@dataclass(frozen=True, slots=True)
class AccessDecision:
    principal: LivePrincipal
    action: str
    session_id: str | None


@dataclass(frozen=True, slots=True)
class CaptureCredential:
    device_id: str
    device_token: str
    scope: Literal["capture"] = "capture"


@dataclass(frozen=True, slots=True)
class ViewCredential:
    session_id: str
    owner_device_id: str
    view_token: str
    expires_at: float
    scope: Literal["view"] = "view"


@dataclass(frozen=True, slots=True)
class RevocationResult:
    device_id: str
    session_ids: tuple[str, ...]


@dataclass(slots=True)
class _PairingState:
    secret_digest: str
    cert_sha256: str
    expires_at: float
    used: bool = False


@dataclass(slots=True)
class _DeviceState:
    device_id: str
    token_digest: str | None
    paired_at: float | None
    revoked: bool = False
    revoked_at: float | None = None


@dataclass(slots=True)
class _SessionState:
    owner_device_id: str
    view_token_digest: str
    bound_at: float
    view_expires_at: float
    view_revoked: bool = False


SecretFactory = Callable[[int], str]

# Reports the live status of a session, or None when the lifecycle owner has never
# heard of it. This is what view authority is derived from, so it is the runtime's
# own view of the session, never a copy of it.
SessionStatusResolver = Callable[[str], str | None]


class LiveAccessRegistry:
    """Single live authorization source for peer, pairing, credential, and ownership state."""

    def __init__(
        self,
        *,
        state_path: str | Path,
        server_cert_sha256: str,
        secret_factory: SecretFactory | None = None,
    ) -> None:
        self._state_path = Path(state_path)
        self._server_cert_sha256 = _normalize_cert_sha256(server_cert_sha256)
        self._secret_factory = secret_factory or _token_urlsafe
        self._pairings: dict[str, _PairingState] = {}
        self._devices: dict[str, _DeviceState] = {}
        self._sessions: dict[str, _SessionState] = {}
        self._session_status: SessionStatusResolver | None = None
        self._load()

    def bind_session_lifecycle(self, session_status: SessionStatusResolver) -> None:
        """Wire the live session lifecycle that view authority is derived from.

        The lifecycle owner (the live runtime) is built after this registry, so this
        cannot be a constructor argument. Until it is wired the registry grants no view
        authority at all: authority that is not bound to a session lifecycle is exactly
        what this method exists to prevent.
        """
        self._session_status = session_status

    def issue_pairing(self, peer: LivePeer, now: float) -> PairingGrant:
        self._admit_peer(peer)
        if not peer.is_loopback:
            raise LiveAccessForbidden("pairing issue requires a loopback peer.")
        secret = self._new_secret()
        secret_digest = _digest(secret)
        expires_at = now + PAIRING_TTL_SECONDS
        self._pairings[secret_digest] = _PairingState(
            secret_digest=secret_digest,
            cert_sha256=self._server_cert_sha256,
            expires_at=expires_at,
        )
        return PairingGrant(
            pairing_payload=f"{PAIRING_PAYLOAD_PREFIX}.{secret}.{self._server_cert_sha256}",
            expires_at=expires_at,
        )

    def exchange_pairing(
        self,
        peer: LivePeer,
        payload: str,
        device_id: str,
        now: float,
    ) -> CaptureCredential:
        self._admit_peer(peer)
        if peer.is_loopback or peer.scheme != "https":
            raise LiveAccessForbidden("pairing exchange requires a non-loopback TLS peer.")
        secret, cert_sha256 = self._parse_pairing_payload(payload)
        if cert_sha256 != self._server_cert_sha256:
            raise LiveAccessUnauthorized("pairing payload is not bound to this certificate.")
        secret_digest = _digest(secret)
        grant = self._pairings.get(secret_digest)
        if grant is None or grant.used:
            raise LiveAccessUnauthorized("pairing payload is invalid.")
        if now >= grant.expires_at:
            raise LiveAccessUnauthorized("pairing payload is expired.")
        if grant.cert_sha256 != self._server_cert_sha256:
            raise LiveAccessUnauthorized("pairing payload is not bound to this certificate.")
        existing = self._devices.get(device_id)
        if existing is not None and existing.revoked:
            raise LiveAccessConflict("device is revoked.")
        device_token = self._new_secret()
        self._devices[device_id] = _DeviceState(
            device_id=device_id,
            token_digest=_digest(device_token),
            paired_at=now,
        )
        grant.used = True
        self._persist()
        return CaptureCredential(device_id=device_id, device_token=device_token)

    def authorize(
        self,
        peer: LivePeer,
        bearer: str | None,
        action: str,
        session_id: str | None,
        now: float,
    ) -> AccessDecision:
        self._admit_peer(peer)
        if action == "descriptor" and session_id is None:
            return AccessDecision(
                principal=DescriptorPrincipal(),
                action=action,
                session_id=None,
            )
        if not bearer:
            raise LiveAccessUnauthorized("missing bearer authority.")
        digest = _digest(bearer)
        capture = self._capture_for_digest(digest)
        if capture is not None:
            if action not in CAPTURE_ACTIONS:
                raise LiveAccessForbidden("capture authority cannot perform this action.")
            if session_id is not None:
                session = self._sessions.get(session_id)
                if session is None:
                    raise LiveAccessForbidden("session is not owned by this device.")
                if session.owner_device_id != capture.device_id:
                    raise LiveAccessForbidden("session is not owned by this device.")
            return AccessDecision(
                principal=CapturePrincipal(device_id=capture.device_id),
                action=action,
                session_id=session_id,
            )
        view = self._view_for_digest(digest, now=now)
        if view is not None:
            if action not in VIEW_ACTIONS:
                raise LiveAccessForbidden("view authority cannot perform this action.")
            if session_id != view.session_id:
                raise LiveAccessForbidden("view authority is scoped to a different session.")
            return AccessDecision(
                principal=ViewPrincipal(session_id=view.session_id),
                action=action,
                session_id=session_id,
            )
        raise LiveAccessUnauthorized("invalid bearer authority.")

    def bind_session(self, capture_principal: CapturePrincipal, session_id: str, now: float) -> ViewCredential:
        device = self._devices.get(capture_principal.device_id)
        if device is None or device.revoked:
            raise LiveAccessForbidden("capture principal is not active.")
        view_token = self._new_secret()
        expires_at = now + VIEW_ABSOLUTE_CAP_SECONDS
        self._sessions[session_id] = _SessionState(
            owner_device_id=capture_principal.device_id,
            view_token_digest=_digest(view_token),
            bound_at=now,
            view_expires_at=expires_at,
        )
        return ViewCredential(
            session_id=session_id,
            owner_device_id=capture_principal.device_id,
            view_token=view_token,
            expires_at=expires_at,
        )

    def revoke_device(self, peer: LivePeer, device_id: str, now: float) -> RevocationResult:
        self._admit_peer(peer)
        if not peer.is_loopback:
            raise LiveAccessForbidden("device revocation requires a loopback peer.")
        device = self._devices.get(device_id)
        if device is None:
            device = _DeviceState(device_id=device_id, token_digest=None, paired_at=None)
            self._devices[device_id] = device
        device.revoked = True
        device.revoked_at = now
        owned = tuple(
            session_id
            for session_id, session in tuple(self._sessions.items())
            if session.owner_device_id == device_id
        )
        for session_id in owned:
            self._sessions.pop(session_id, None)
        self._persist()
        return RevocationResult(device_id=device_id, session_ids=owned)

    def revoke_view(self, peer: LivePeer, session_id: str, now: float) -> bool:
        """Operator revocation of one session's view authority.

        Capture ownership survives, so the meeting keeps streaming and can still be
        stopped cleanly; only the browser's authority dies, and it dies at once.
        """
        self._admit_peer(peer)
        if not peer.is_loopback:
            raise LiveAccessForbidden("view revocation requires a loopback peer.")
        session = self._sessions.get(session_id)
        if session is None or session.view_revoked:
            return False
        session.view_revoked = True
        return True

    def release_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _admit_peer(self, peer: LivePeer) -> None:
        try:
            address = peer.address
        except ValueError as exc:
            raise LiveAccessForbidden("invalid peer address.") from exc
        if not any(address in network for network in _ALLOWED_PEER_NETWORKS):
            raise LiveAccessForbidden("peer is outside the private live network.")
        if not peer.is_loopback and peer.scheme != "https":
            raise LiveAccessForbidden("non-loopback live access requires TLS.")

    def _new_secret(self) -> str:
        return self._secret_factory(SECRET_BYTES)

    def _parse_pairing_payload(self, payload: str) -> tuple[str, str]:
        parts = payload.split(".")
        if len(parts) != 3 or parts[0] != PAIRING_PAYLOAD_PREFIX:
            raise LiveAccessUnauthorized("pairing payload is invalid.")
        secret = parts[1]
        try:
            cert_sha256 = _normalize_cert_sha256(parts[2])
        except ValueError as exc:
            raise LiveAccessUnauthorized("pairing payload is invalid.") from exc
        return secret, cert_sha256

    def _capture_for_digest(self, token_digest: str) -> _DeviceState | None:
        for device in self._devices.values():
            if device.token_digest == token_digest and not device.revoked:
                return device
        return None

    def _view_for_digest(self, token_digest: str, *, now: float) -> ViewPrincipal | None:
        for session_id, session in self._sessions.items():
            if session.view_token_digest != token_digest:
                continue
            if session.view_revoked or now >= session.view_expires_at:
                return None
            if not self._session_is_viewable(session_id):
                return None
            return ViewPrincipal(session_id=session_id)
        return None

    def _session_is_viewable(self, session_id: str) -> bool:
        if self._session_status is None:
            return False
        return self._session_status(session_id) in VIEWABLE_SESSION_STATUSES

    def _load(self) -> None:
        if not self._state_path.exists():
            return
        data = json.loads(self._state_path.read_text(encoding="utf-8"))
        devices = data.get("devices", {})
        if not isinstance(devices, dict):
            raise ValueError("live auth state devices must be an object.")
        for device_id, item in devices.items():
            if not isinstance(item, dict):
                raise ValueError("live auth state device entries must be objects.")
            token_digest = item.get("token_digest")
            paired_at = item.get("paired_at")
            revoked_at = item.get("revoked_at")
            self._devices[str(device_id)] = _DeviceState(
                device_id=str(device_id),
                token_digest=str(token_digest) if token_digest is not None else None,
                paired_at=float(paired_at) if paired_at is not None else None,
                revoked=bool(item.get("revoked", False)),
                revoked_at=float(revoked_at) if revoked_at is not None else None,
            )

    def _persist(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "devices": {
                device_id: {
                    "token_digest": device.token_digest,
                    "paired_at": device.paired_at,
                    "revoked": device.revoked,
                    "revoked_at": device.revoked_at,
                }
                for device_id, device in sorted(self._devices.items())
            },
        }
        tmp_path = self._state_path.with_name(f".{self._state_path.name}.{os.getpid()}.tmp")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            with os.fdopen(os.open(tmp_path, flags, 0o600), "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_path, self._state_path)
            if os.name != "nt":
                os.chmod(self._state_path, 0o600)
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token_urlsafe(nbytes: int) -> str:
    return secrets.token_urlsafe(nbytes)


def _normalize_cert_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ValueError("server certificate SHA-256 must be 64 hex characters.")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError("server certificate SHA-256 must be 64 hex characters.") from exc
    return normalized
