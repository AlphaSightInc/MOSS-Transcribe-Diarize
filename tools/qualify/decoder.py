"""Owned loopback forward: exact dispatched-call/peak accounting without bodies in logs."""
import http.client
import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _carries_error_payload(payload, content_type):
    def is_error_object(value):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        return isinstance(decoded, dict) and 'error' in decoded

    if 'text/event-stream' in content_type.lower():
        for line in payload.splitlines():
            line = line.strip()
            if line.startswith(b'event:') and line[6:].strip() == b'error':
                return True
            if line.startswith(b'data:') and is_error_object(line[5:].strip()):
                return True
        return False
    return is_error_object(payload)


@dataclass(frozen=True, slots=True)
class DecoderCounters:
    accepted: int
    completed: int
    upstream_failed: int
    client_write_failed: int
    rejected: int
    active: int
    peak_in_flight: int
    distinct_attempt_ids: int
    distinct_completed_attempt_ids: int
    distinct_client_request_ids: int
    duplicate_attempts: int
    unowned_events: int
    missing_client_request_ids: int


@dataclass(frozen=True, slots=True)
class ProxyEventSummary:
    attempted: int
    completed: int
    upstream_failed: int
    client_write_failed: int
    rejected: int
    active: int
    peak_in_flight: int
    distinct_attempt_ids: int
    distinct_completed_attempt_ids: int
    distinct_client_request_ids: int
    duplicate_attempts: int
    unowned_events: int
    missing_client_request_ids: int
    wrong_row_events: int
    row_owners: tuple[str, ...]
    event_count: int
    reconciled: bool


def read_events(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def summarize_events(events, *, expected_row=None):
    attempted = [event for event in events if event.get('kind') == 'start']
    completed = [event for event in events if event.get('kind') == 'end']
    failed = [event for event in events if event.get('kind') == 'upstream_failed']
    client_write_failed = [
        event for event in events if event.get('kind') == 'client_write_failed'
    ]
    rejected = [event for event in events if event.get('kind') == 'reject']
    attempt_ids = [event.get('attempt_id') for event in attempted]
    outcome_ids = [event.get('attempt_id') for event in completed + failed]
    completed_attempt_ids = [event.get('attempt_id') for event in completed]
    client_request_ids = [
        event.get('client_request_id')
        for event in attempted
        if event.get('client_request_id')
    ]
    row_owners = tuple(sorted({
        str(event['row']) for event in events if event.get('row')
    }))
    active = int(events[-1].get('active', 0)) if events else 0
    return ProxyEventSummary(
        attempted=len(attempted),
        completed=len(completed),
        upstream_failed=len(failed),
        client_write_failed=len(client_write_failed),
        rejected=len(rejected),
        active=active,
        peak_in_flight=max((int(event.get('active', 0)) for event in events), default=0),
        distinct_attempt_ids=len(set(attempt_ids)),
        distinct_completed_attempt_ids=len(set(completed_attempt_ids)),
        distinct_client_request_ids=len(set(client_request_ids)),
        duplicate_attempts=len(client_request_ids) - len(set(client_request_ids)),
        unowned_events=sum(not event.get('row') for event in events),
        missing_client_request_ids=sum(
            not event.get('client_request_id') for event in attempted
        ),
        wrong_row_events=sum(
            expected_row is not None and event.get('row') != expected_row
            for event in events
        ),
        row_owners=row_owners,
        event_count=len(events),
        reconciled=(
            active == 0
            and len(attempted) == len(completed) + len(failed)
            and all(attempt_ids)
            and all(outcome_ids)
            and len(attempt_ids) == len(set(attempt_ids))
            and len(outcome_ids) == len(set(outcome_ids))
            and set(attempt_ids) == set(outcome_ids)
        ),
    )


def accounting_incomplete(summary, *, planned=None):
    return bool(
        summary.upstream_failed
        or summary.client_write_failed
        or summary.rejected
        or not summary.reconciled
        or summary.duplicate_attempts
        or summary.unowned_events
        or summary.wrong_row_events
        or (
            planned is not None
            and (
                summary.attempted != planned
                or summary.completed != planned
                or summary.distinct_attempt_ids != planned
                or summary.distinct_completed_attempt_ids != planned
            )
        )
    )


class Decoder:
    def __init__(self, port, tunnel_port, budget, log):
        self.sent = self.completed = self.upstream_failed = self.client_write_failed = 0
        self.active = self.peak = self.rejected = 0
        self.duplicate_attempts = self.unowned_events = 0
        self.missing_client_request_ids = 0
        self.next_attempt_id = 0
        self.attempt_ids = set()
        self.completed_attempt_ids = set()
        self.client_request_ids = set()
        self.row_owner = None
        self.budget, self.tunnel_port, self.log = budget, tunnel_port, log
        self.lock = threading.Lock()
        self.activity = threading.Condition(self.lock)
        self.slots = threading.BoundedSemaphore(2)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                requested_row = self.headers.get('X-MOSS-Qualification-Row')
                client_request_id = self.headers.get('X-Request-ID') or None
                with owner.slots:
                    with owner.lock:
                        row = requested_row or owner.row_owner
                        if owner.sent >= owner.budget:
                            owner.rejected += 1
                            owner.event(
                                'reject', row=row, attempt_id=None,
                                client_request_id=client_request_id,
                            )
                            owner.activity.notify_all()
                            self.send_error(429, 'Local qualification budget exhausted')
                            return
                        owner.sent += 1
                        owner.next_attempt_id += 1
                        attempt_id = f'attempt-{owner.next_attempt_id}'
                        owner.attempt_ids.add(attempt_id)
                        owner.active += 1
                        owner.peak = max(owner.peak, owner.active)
                        if client_request_id:
                            if client_request_id in owner.client_request_ids:
                                owner.duplicate_attempts += 1
                            owner.client_request_ids.add(client_request_id)
                        else:
                            owner.missing_client_request_ids += 1
                        owner.event(
                            'start', row=row, attempt_id=attempt_id,
                            client_request_id=client_request_id,
                        )
                        owner.activity.notify_all()
                    conn = http.client.HTTPConnection('127.0.0.1', owner.tunnel_port, timeout=1800)
                    upstream_status = None
                    error_type = None
                    relayed = False
                    payload = None
                    response_content_type = 'application/json'
                    try:
                        headers = {k: v for k, v in self.headers.items()
                                   if k.lower() not in ('host', 'connection', 'transfer-encoding')}
                        conn.request('POST', self.path, body, headers)
                        response = conn.getresponse()
                        upstream_status = response.status
                        payload = response.read()
                        response_content_type = response.getheader('Content-Type', 'application/json')
                        carries_error = _carries_error_payload(payload, response_content_type)
                        relayed = 200 <= response.status < 300 and not carries_error
                        if carries_error:
                            error_type = 'UpstreamErrorPayload'
                    except (OSError, http.client.HTTPException) as exc:
                        error_type = type(exc).__name__
                    finally:
                        conn.close()
                        with owner.lock:
                            owner.active -= 1
                            if relayed:
                                owner.completed += 1
                                owner.completed_attempt_ids.add(attempt_id)
                                owner.event(
                                    'end', row=row, attempt_id=attempt_id,
                                    client_request_id=client_request_id,
                                    upstream_status=upstream_status,
                                )
                            else:
                                owner.upstream_failed += 1
                                owner.event(
                                    'upstream_failed', row=row, attempt_id=attempt_id,
                                    client_request_id=client_request_id,
                                    upstream_status=upstream_status, error_type=error_type,
                                )
                            owner.activity.notify_all()
                    try:
                        if payload is None:
                            self.send_error(502, 'Owned decoder forward failed')
                        else:
                            self.send_response(upstream_status)
                            self.send_header('Content-Type', response_content_type)
                            self.send_header('Content-Length', str(len(payload)))
                            self.end_headers()
                            self.wfile.write(payload)
                    except OSError as exc:
                        with owner.lock:
                            owner.client_write_failed += 1
                            owner.event(
                                'client_write_failed', row=row, attempt_id=attempt_id,
                                client_request_id=client_request_id,
                                upstream_status=upstream_status,
                                error_type=type(exc).__name__,
                            )
                            owner.activity.notify_all()

            def do_GET(self):
                conn = http.client.HTTPConnection('127.0.0.1', owner.tunnel_port, timeout=10)
                try:
                    conn.request('GET', self.path)
                    response = conn.getresponse()
                    payload = response.read()
                    self.send_response(response.status)
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                finally:
                    conn.close()

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def event(self, kind, *, row, attempt_id, client_request_id, **outcome):
        if not row:
            self.unowned_events += 1
        with self.log.open('a') as stream:
            stream.write(json.dumps(dict(kind=kind, time=time.monotonic(), sent=self.sent,
                                         completed=self.completed, rejected=self.rejected,
                                         upstream_failed=self.upstream_failed,
                                         active=self.active, peak=self.peak, row=row,
                                         attempt_id=attempt_id,
                                         client_request_id=client_request_id,
                                         **outcome))+'\n')

    def set_row_owner(self, row):
        with self.lock:
            self.row_owner = row

    def clear_row_owner(self, row):
        with self.lock:
            if self.row_owner == row:
                self.row_owner = None

    def _wait_until_idle_locked(self, settle_seconds):
        observed_attempts = (self.sent, self.rejected)
        idle_since = None
        while True:
            attempts = (self.sent, self.rejected)
            if attempts != observed_attempts:
                observed_attempts = attempts
                idle_since = None
            if self.active:
                idle_since = None
                self.activity.wait()
                continue
            now = time.monotonic()
            if idle_since is None:
                idle_since = now
            remaining = settle_seconds - (now - idle_since)
            if remaining <= 0:
                return
            self.activity.wait(timeout=remaining)

    def wait_until_idle(self, settle_seconds):
        """Wait for no active request and no accepted/rejected attempt during settle."""
        with self.activity:
            self._wait_until_idle_locked(settle_seconds)

    def settle_row_owner(self, row, settle_seconds):
        """Atomically wait for a quiet proxy and release this row's ownership."""
        with self.activity:
            self._wait_until_idle_locked(settle_seconds)
            if self.row_owner == row:
                self.row_owner = None

    def start(self):
        self.thread.start()

    def snapshot(self) -> DecoderCounters:
        with self.lock:
            return DecoderCounters(
                accepted=self.sent,
                completed=self.completed,
                upstream_failed=self.upstream_failed,
                client_write_failed=self.client_write_failed,
                rejected=self.rejected,
                active=self.active,
                peak_in_flight=self.peak,
                distinct_attempt_ids=len(self.attempt_ids),
                distinct_completed_attempt_ids=len(self.completed_attempt_ids),
                distinct_client_request_ids=len(self.client_request_ids),
                duplicate_attempts=self.duplicate_attempts,
                unowned_events=self.unowned_events,
                missing_client_request_ids=self.missing_client_request_ids,
            )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
