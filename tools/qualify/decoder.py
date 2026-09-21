"""Owned loopback forward: exact dispatched-call/peak accounting without bodies in logs."""
import http.client
import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass(frozen=True, slots=True)
class DecoderCounters:
    accepted: int
    completed: int
    upstream_failed: int
    rejected: int
    active: int
    peak_in_flight: int
    distinct_request_ids: int
    distinct_completed_request_ids: int
    duplicate_attempts: int
    unowned_events: int
    missing_request_ids: int


@dataclass(frozen=True, slots=True)
class ProxyEventSummary:
    attempted: int
    completed: int
    upstream_failed: int
    rejected: int
    active: int
    peak_in_flight: int
    distinct_request_ids: int
    distinct_completed_request_ids: int
    duplicate_attempts: int
    unowned_events: int
    missing_request_ids: int
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
    rejected = [event for event in events if event.get('kind') == 'reject']
    request_ids = [event.get('request_id') for event in attempted if event.get('request_id')]
    completed_ids = {
        event.get('request_id') for event in completed if event.get('request_id')
    }
    row_owners = tuple(sorted({
        str(event['row']) for event in events if event.get('row')
    }))
    active = int(events[-1].get('active', 0)) if events else 0
    return ProxyEventSummary(
        attempted=len(attempted),
        completed=len(completed),
        upstream_failed=len(failed),
        rejected=len(rejected),
        active=active,
        peak_in_flight=max((int(event.get('active', 0)) for event in events), default=0),
        distinct_request_ids=len(set(request_ids)),
        distinct_completed_request_ids=len(completed_ids),
        duplicate_attempts=len(request_ids) - len(set(request_ids)),
        unowned_events=sum(not event.get('row') for event in events),
        missing_request_ids=sum(not event.get('request_id') for event in events),
        wrong_row_events=sum(
            expected_row is not None and event.get('row') != expected_row
            for event in events
        ),
        row_owners=row_owners,
        event_count=len(events),
        reconciled=active == 0 and len(attempted) == len(completed) + len(failed),
    )


def accounting_incomplete(summary, *, planned=None):
    return bool(
        summary.upstream_failed
        or summary.rejected
        or not summary.reconciled
        or summary.duplicate_attempts
        or summary.unowned_events
        or summary.missing_request_ids
        or summary.wrong_row_events
        or (
            planned is not None
            and (
                summary.attempted != planned
                or summary.completed != planned
                or summary.distinct_request_ids != planned
                or summary.distinct_completed_request_ids != planned
            )
        )
    )


class Decoder:
    def __init__(self, port, tunnel_port, budget, log):
        self.sent = self.completed = self.upstream_failed = 0
        self.active = self.peak = self.rejected = 0
        self.duplicate_attempts = self.unowned_events = self.missing_request_ids = 0
        self.request_ids = set()
        self.completed_request_ids = set()
        self.row_owner = None
        self.budget, self.tunnel_port, self.log = budget, tunnel_port, log
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                row = self.headers.get('X-MOSS-Qualification-Row') or owner.row_owner
                request_id = self.headers.get('X-Request-ID') or None
                with owner.slots:
                    with owner.lock:
                        if owner.sent >= owner.budget:
                            owner.rejected += 1
                            owner.event('reject', row=row, request_id=request_id)
                            self.send_error(429, 'Local qualification budget exhausted')
                            return
                        owner.sent += 1
                        owner.active += 1
                        owner.peak = max(owner.peak, owner.active)
                        if request_id:
                            if request_id in owner.request_ids:
                                owner.duplicate_attempts += 1
                            owner.request_ids.add(request_id)
                        owner.event('start', row=row, request_id=request_id)
                    conn = http.client.HTTPConnection('127.0.0.1', owner.tunnel_port, timeout=1800)
                    upstream_status = None
                    error_type = None
                    relayed = False
                    try:
                        headers = {k: v for k, v in self.headers.items()
                                   if k.lower() not in ('host', 'connection', 'transfer-encoding')}
                        conn.request('POST', self.path, body, headers)
                        response = conn.getresponse()
                        upstream_status = response.status
                        payload = response.read()
                        self.send_response(response.status)
                        self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                        self.send_header('Content-Length', str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        relayed = 200 <= response.status < 300
                    except (OSError, http.client.HTTPException) as exc:
                        error_type = type(exc).__name__
                        try:
                            self.send_error(502, 'Owned decoder forward failed')
                        except OSError:
                            pass
                    finally:
                        conn.close()
                        with owner.lock:
                            owner.active -= 1
                            if relayed:
                                owner.completed += 1
                                if request_id:
                                    owner.completed_request_ids.add(request_id)
                                owner.event(
                                    'end', row=row, request_id=request_id,
                                    upstream_status=upstream_status,
                                )
                            else:
                                owner.upstream_failed += 1
                                owner.event(
                                    'upstream_failed', row=row, request_id=request_id,
                                    upstream_status=upstream_status, error_type=error_type,
                                )

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

    def event(self, kind, *, row, request_id, **outcome):
        if not row:
            self.unowned_events += 1
        if not request_id:
            self.missing_request_ids += 1
        with self.log.open('a') as stream:
            stream.write(json.dumps(dict(kind=kind, time=time.monotonic(), sent=self.sent,
                                         completed=self.completed, rejected=self.rejected,
                                         upstream_failed=self.upstream_failed,
                                         active=self.active, peak=self.peak, row=row,
                                         request_id=request_id, **outcome))+'\n')

    def set_row_owner(self, row):
        with self.lock:
            self.row_owner = row

    def clear_row_owner(self, row):
        with self.lock:
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
                rejected=self.rejected,
                active=self.active,
                peak_in_flight=self.peak,
                distinct_request_ids=len(self.request_ids),
                distinct_completed_request_ids=len(self.completed_request_ids),
                duplicate_attempts=self.duplicate_attempts,
                unowned_events=self.unowned_events,
                missing_request_ids=self.missing_request_ids,
            )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
