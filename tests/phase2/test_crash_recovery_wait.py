from moss_transcribe_diarize.phase2_acceptance_external import ExternalMeasurementError, _wait_crash_recovery


class FakeOps:
    def __init__(self, *, replace=True, ready=True):
        self.now = 0.0
        self.replace = replace
        self.becomes_ready = ready
        self.ready_calls = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def pid(self, unit, timeout):
        assert unit == 'moss-web.service' and 0 < timeout <= 1
        if self.now < 1:
            raise ExternalMeasurementError('service is restarting')
        return 222 if self.replace else 111

    def ready(self, timeout):
        assert 0 < timeout <= 1
        self.ready_calls += 1
        if self.now < 2:
            raise ExternalMeasurementError('connection refused')
        return self.becomes_ready


def test_crash_wait_requires_replaced_pid_and_http_readiness():
    ops = FakeOps()
    result = _wait_crash_recovery(ops, 'moss-web.service', 111, timeout=5)
    assert result['ready'] is True and result['new_pid'] == 222
    assert result['wait_seconds'] == 2 and result['polls'] == 5
    assert ops.ready_calls == 3


def test_crash_wait_bounds_missing_restart_and_never_accepts_old_ready_process():
    ops = FakeOps(replace=False)
    result = _wait_crash_recovery(ops, 'moss-web.service', 111, timeout=3)
    assert result['ready'] is False and result['wait_seconds'] == 3
    assert ops.ready_calls == 0


def test_crash_wait_bounds_new_process_that_never_becomes_ready():
    result = _wait_crash_recovery(FakeOps(ready=False), 'moss-web.service', 111, timeout=3)
    assert result['ready'] is False and result['new_pid'] == 222
    assert result['wait_seconds'] == 3
