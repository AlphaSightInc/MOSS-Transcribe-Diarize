"""P74-RS product routes, offline recognition and exact decoded archive clock."""
import importlib.util
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Reuse the measured offline bench's audio/app fixtures, never its patched transport.
BENCH = Path(__file__).resolve().parents[2] / 'prototypes/gemini-live/long-meeting/resume'
sys.path.insert(0, str(BENCH))
spec = importlib.util.spec_from_file_location('resume_bench', BENCH / 'run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.fixture
def live(tmp_path, request):
    app, cookies, engines = bench.build_app(tmp_path / 'resume')
    clock, timer = bench.Clock(), bench.FakeTimer()
    with TestClient(app, base_url='https://moss.test') as client:
        bench.session(client, cookies['a'])
        st = app.state
        st.resume_evidence_root = tmp_path / 'resume'
        st.live_helper_presence._monotonic_ns = clock
        st.live_helper_failures._monotonic_ns = clock
        st.live_helper_failures._timer = timer
        sid = client.post('/api/live/sessions', json={'engine_settings': {**bench.SETTINGS, 'cleanup_after_stop': getattr(request, 'param', False)}}).json()['id']
        base = f'/api/live/sessions/{sid}'
        old = {'X-Moss-Capture-Instance': 'old'}
        assert client.post(base + '/heartbeat', json=bench.hb('old'), headers=old).status_code == 200
        yield client, st, cookies, engines, clock, timer, sid, base, old


def resume(client, base, instance='new', expected='old', automatic=False):
    return client.post(base + '/resume', json={'expected_instance_id': expected,
        'instance_id': instance, 'automatic': automatic})


def prefix(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    origin = clock.now
    for i in range(8):
        clock.now = origin + (i + 1) * 500_000_000
        for lane in ('system', 'microphone'):
            assert client.post(base + '/frames', json=bench.frame(lane, i, i * .5), headers=old).status_code == 200
    assert client.post(base + '/heartbeat', json=bench.hb('old', 1), headers=old).status_code == 200


@pytest.mark.parametrize('gap', [5, 30, 90, 119, 125])
def test_resume_gap_archive_and_terminal(live, gap):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += gap * bench.NS
    response = resume(client, base)
    if gap >= 120:
        assert response.status_code == 409
        assert response.json()['code'] == 'resume_lease_expired'
        assert bench.wait_meeting(client, sid, 'interrupted')['status'] == 'interrupted'
        assert resume(client, base).status_code == 409
        return
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['session_id'] == sid and state['instance_id'] == 'new'
    assert state['descriptor']['sample_rate'] == bench.RATE
    assert state['capture_now_ns'] == (4 + gap) * bench.NS
    assert state['interruption'] == {'start_sample': 4 * bench.RATE, 'end_sample': None}
    assert state['heartbeat_next_sequence'] == 2
    new = {'X-Moss-Capture-Instance': 'new'}
    for i in range(8):
        for lane in ('system', 'microphone'):
            cursor = state['lanes'][lane]
            assert cursor['next_sequence'] == 8
            r = client.post(base + '/frames', headers=new,
                json=bench.frame(lane, 8 + i, 4 + gap + i * .5, cursor['resume_device_epoch'], i == 0))
            assert r.status_code == 200, r.text
    gap_row = {'start_sample': 4 * bench.RATE, 'end_sample': (4 + gap) * bench.RATE}
    snapshot = client.get(base + '/snapshot').json()
    assert snapshot['snapshot']['session']['capture_interruptions'] == [gap_row]
    assert snapshot['snapshot']['session']['sample_rate'] == bench.RATE
    assert 'capture_interruptions' not in snapshot
    assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
    meeting = bench.wait_meeting(client, sid, 'completed')
    assert meeting['transcript']['capture_interruptions'] == [gap_row]
    assert meeting['transcript']['sample_rate'] == bench.RATE
    assert len(engines) == 1
    archive = list((st.resume_evidence_root / 'meetings').glob('**/audio.mp3'))
    # The fixture's database and audio directory share a disposable evidence root.
    assert len(archive) == 1
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(archive[0]), '-f', 's16le', '-ac', '1', '-ar', str(bench.RATE), '-'])
    assert len(pcm) // 2 == (8 + gap) * bench.RATE
    assert set(pcm[int(4.1 * bench.RATE) * 2:int((4 + gap - .1) * bench.RATE) * 2]) == {0}


def test_automatic_liveness_and_explicit_takeover(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    before = st.live_helper_failures.arm(sid)
    assert resume(client, base, automatic=True).json() == {
        'code': 'capture_page_alive', 'retry_after_ms': 3000}
    clock.now += 2_999_999_999
    waiting = resume(client, base, automatic=True)
    assert waiting.status_code == 409
    assert waiting.json() == {'code': 'capture_page_alive', 'retry_after_ms': 1}
    assert st.live_helper_failures.snapshot(sid) == before
    clock.now += 1
    accepted = resume(client, base, automatic=True)
    assert accepted.status_code == 200
    lease = st.live_helper_failures.snapshot(sid)
    assert lease.generation == before.generation + 1
    clock.now += bench.NS
    assert resume(client, base, automatic=True).json() == accepted.json()
    assert st.live_helper_failures.snapshot(sid) == lease
    assert resume(client, base, instance='user', expected='new').status_code == 200


def test_automatic_wait_tracks_real_heartbeats_past_client_retry_window(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    # A duplicated page remains a viewer while the original keeps heartbeating.
    for sequence in range(1, 6):
        clock.now += 2 * bench.NS
        assert client.post(base + '/heartbeat', json=bench.hb('old', sequence), headers=old).status_code == 200
        lease = st.live_helper_failures.snapshot(sid)
        clock.now += 500_000_000
        waiting = resume(client, base, automatic=True)
        assert waiting.status_code == 409
        assert waiting.json() == {'code': 'capture_page_alive', 'retry_after_ms': 2500}
        assert st.live_helper_failures.snapshot(sid) == lease
        assert st.live_helper_presence.snapshot(sid).instance_id == 'old'
    clock.now += 2_500_000_000
    assert resume(client, base, automatic=True).status_code == 200


@pytest.mark.parametrize('operation', ['frames', 'heartbeat', 'stop', 'abort'])
@pytest.mark.parametrize('header', ['old', None])
def test_replaced_writer_fenced_before_mutation(live, operation, header):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    assert resume(client, base).status_code == 200
    payload = {'frames': bench.frame('system', 0, 0), 'heartbeat': bench.hb('old', 1),
               'stop': {'deadline': 10}, 'abort': {'reason': 'stale'}}[operation]
    r = client.post(base + '/' + operation, json=payload,
        headers={} if header is None else {'X-Moss-Capture-Instance': header})
    assert (r.status_code, r.json()['code']) == (409, 'capture_replaced')
    assert client.get(f'/api/meetings/{sid}').json()['status'] == 'active'


def test_resume_origin_authority_cas_and_malformed(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    async def other_signin():
        await st.phase2_store._connection.execute(
            'INSERT INTO sign_in_sessions VALUES (?, ?, ?)', ('resume-other-signin', 'sub-a', 1))
        await st.phase2_store._connection.commit()
    client.portal.call(other_signin)
    bench.session(client, 'resume-other-signin')
    assert resume(client, base).status_code == 403
    bench.session(client, cookies['b'])
    assert resume(client, base).status_code == 404
    bench.session(client, cookies['a'])
    before = st.live_helper_presence.snapshot(sid)
    for payload in ({}, {'expected_instance_id': 'old', 'instance_id': '', 'automatic': False},
                    {'expected_instance_id': 'old', 'instance_id': 'new', 'automatic': 'false'}):
        assert client.post(base + '/resume', json=payload).status_code == 400
        assert st.live_helper_presence.snapshot(sid) == before
    assert resume(client, base, expected='wrong').json()['code'] == 'capture_writer_mismatch'
    assert resume(client, base, expected=None).status_code == 200


def test_concurrent_resume_one_winner_and_heartbeat_order(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda name: resume(client, base, instance=name), ('one', 'two')))
    assert sorted(r.status_code for r in results) == [200, 409]
    state = next(r.json() for r in results if r.status_code == 200)
    hb = bench.hb(state['instance_id'], state['heartbeat_next_sequence'])
    hb['sent_monotonic_ns'] = state['heartbeat_next_monotonic_ns']
    new = {'X-Moss-Capture-Instance': state['instance_id']}
    assert client.post(base + '/heartbeat', json=hb, headers=new).status_code == 200
    assert client.post(base + '/heartbeat', json=bench.hb('old', 1), headers=new).status_code == 409
    assert resume(client, base, instance='third').json()['code'] == 'capture_writer_mismatch'


def test_stop_accepted_first_and_expired_never_reopen(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    assert client.post(base + '/stop', json={'deadline': 20}, headers=old).status_code == 200
    assert resume(client, base).status_code == 409
    assert bench.wait_meeting(client, sid, 'completed')['status'] == 'completed'


@pytest.mark.parametrize('takeover', [False, True], ids=['detached-inside-lease', 'resumed-writer'])
def test_text_edit_and_delete_refused_inside_resume_lease(live, takeover):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    client.portal.call(st.phase2_live.sync_and_flush, sid)
    clock.now += 5 * bench.NS
    if takeover:
        assert resume(client, base).status_code == 200
    before = client.get(f'/api/meetings/{sid}').json()
    passage = before['transcript']['segments'][0]['id']
    assert before['status'] == 'active'
    lease = st.live_helper_failures.snapshot(sid)
    assert client.put(f'/api/meetings/{sid}/passages/{passage}/text',
                      json={'text': 'must not replace live speech'}).status_code == 409
    assert client.delete(f'/api/meetings/{sid}').status_code == 409
    assert client.delete('/api/meetings').json() == {
        'deleted': 0, 'kept': [{'meeting_id': sid, 'reason': 'Stop recording first.'}]}
    assert client.get(f'/api/meetings/{sid}').json() == before
    assert st.live_helper_failures.snapshot(sid) == lease


def test_resumed_gap_survives_text_and_speaker_edit_then_deletes_cleanly(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += 5 * bench.NS
    state = resume(client, base).json()
    new = {'X-Moss-Capture-Instance': 'new'}
    for lane in ('system', 'microphone'):
        cursor = state['lanes'][lane]
        accepted = client.post(base + '/frames', headers=new,
            json=bench.frame(lane, cursor['next_sequence'], 9, cursor['resume_device_epoch'], True))
        assert accepted.status_code == 200, accepted.text
    assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
    before = bench.wait_meeting(client, sid, 'completed')
    gaps = before['transcript']['capture_interruptions']
    segments = before['transcript']['segments']
    passage = segments[-1]['id']
    assert client.put(f'/api/meetings/{sid}/passages/{passage}/text',
                      json={'text': 'corrected after interruption'}).status_code == 200
    assert client.put(f'/api/meetings/{sid}/passages/speaker',
                      json={'segment_ids': [passage], 'label': 'Blair'}).status_code == 200
    after = client.get(f'/api/meetings/{sid}').json()
    assert after['transcript']['capture_interruptions'] == gaps
    assert after['transcript']['sample_rate'] == bench.RATE
    assert after['transcript']['segments'][:-1] == segments[:-1]
    selected = after['transcript']['segments'][-1]
    assert (selected['text'], selected['edited'], selected['speaker']) == ('corrected after interruption', True, 'Blair')
    assert client.get('/api/meetings').json()['meetings'][0]['transcript'] == after['transcript']
    archives = list(st.resume_evidence_root.glob('meetings/**/audio.mp3'))
    assert len(archives) == 1
    assert client.delete(f'/api/meetings/{sid}').status_code == 204
    assert client.get(f'/api/meetings/{sid}').status_code == 404
    assert client.get('/api/meetings').json() == {'meetings': []}
    assert not archives[0].exists()


@pytest.mark.parametrize('live', [True], indirect=True)
def test_gap_metadata_survives_refinement_and_summary(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    client.portal.call(st.phase2_live.sync_and_flush, sid)
    release = __import__('asyncio').Event()
    async def finish(tape):
        await release.wait()
        return tuple(bench.GeminiSegment(start, end, 'cleaned audible block', 'speaker-0001')
                     for start, end in engines[0].audio_blocks)
    engines[0].finish = finish
    clock.now += 5 * bench.NS
    assert resume(client, base).status_code == 200
    new = {'X-Moss-Capture-Instance': 'new'}
    for lane in ('system', 'microphone'):
        assert client.post(base + '/frames', json=bench.frame(lane, 8, 9, 1, True), headers=new).status_code == 200
    assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
    detail = bench.wait_meeting(client, sid, 'completed')
    assert detail['refinement_state'] == 'running'
    before = detail['transcript']['capture_interruptions']
    client.portal.call(release.set)
    import time
    for _ in range(100):
        detail = client.get(f'/api/meetings/{sid}').json()
        if detail['refinement_state'] == 'done':
            break
        time.sleep(.02)
    assert detail['refinement_state'] == 'done', detail
    document = detail['transcript']
    assert document['capture_interruptions'] == before
    assert client.get('/api/meetings').json()['meetings'][0]['id'] == sid
    assert document == client.get(f'/api/meetings/{sid}').json()['transcript']
    assert document['sample_rate'] == bench.RATE
    session = client.get(base + '/snapshot').json()['snapshot']['session']
    assert session['capture_interruptions'] == before
    assert session['sample_rate'] == bench.RATE
    assert 'Recording Interrupted' not in json.dumps(document['segments'])
    from moss_transcribe_diarize.app.phase2_summary import MeetingSummaries
    async def source():
        account = await st.phase2_store.account_for_session(cookies['a'])
        handle = await st.phase2_store.workspace(account).open_meeting(sid)
        _, summary_input = await MeetingSummaries(handle).start_server(
            (await handle.snapshot()).transcript_version)
        return summary_input
    summary_input = client.portal.call(source)
    assert 'capture_interruptions' not in summary_input
    assert 'sample_rate' not in summary_input
    assert 'Recording Interrupted' not in json.dumps(summary_input)
    assert all('Recording Interrupted' not in str(block) for block in engines[0].audio_blocks)


def test_old_ack_replay_fenced_and_resume_epoch_is_required(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += 5 * bench.NS
    state = resume(client, base).json()
    assert client.post(base + '/frames', json=bench.frame('system', 0, 0), headers=old).status_code == 409
    new = {'X-Moss-Capture-Instance': 'new'}
    no_discontinuity = bench.frame('system', 8, 9, state['lanes']['system']['resume_device_epoch'])
    assert client.post(base + '/frames', json=no_discontinuity, headers=new).status_code == 409
    no_discontinuity['discontinuity'] = True
    assert client.post(base + '/frames', json=no_discontinuity, headers=new).status_code == 200


def test_resume_at_exact_deadline_before_callback_is_expiry(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    lease = st.live_helper_failures.arm(sid)
    clock.now = lease.deadline_monotonic_ns
    assert resume(client, base).json()['code'] == 'resume_lease_expired'
    assert bench.wait_meeting(client, sid, 'interrupted')['status'] == 'interrupted'
    assert resume(client, base).status_code == 409


def test_duplicate_resume_does_not_refresh_presence_or_lease(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += 5 * bench.NS
    first = resume(client, base)
    assert first.status_code == 200
    presence = st.live_helper_presence.snapshot(sid)
    lease = st.live_helper_failures.snapshot(sid)
    original_timer_count = len(timer.scheduled)
    clock.now += 90 * bench.NS
    assert resume(client, base).json() == first.json()
    assert resume(client, base, automatic=True).json() == first.json()
    assert st.live_helper_presence.snapshot(sid) == presence
    assert st.live_helper_failures.snapshot(sid) == lease
    assert len(timer.scheduled) == original_timer_count
    # Callback from the replaced generation is harmless.
    client.portal.call(timer.scheduled[-2][1].fire)
    assert client.get(f'/api/meetings/{sid}').json()['status'] == 'active'


def test_two_resumes_have_two_ordered_gaps(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += 5 * bench.NS
    one = resume(client, base).json()
    new = {'X-Moss-Capture-Instance': 'new'}
    for lane in ('system', 'microphone'):
        assert client.post(base + '/frames', json=bench.frame(lane, 8, 9, 1, True), headers=new).status_code == 200
    clock.now += 500_000_000
    hb = bench.hb('new', one['heartbeat_next_sequence'])
    hb['sent_monotonic_ns'] = one['heartbeat_next_monotonic_ns']
    assert client.post(base + '/heartbeat', json=hb, headers=new).status_code == 200
    clock.now += 5 * bench.NS
    two = resume(client, base, 'third', 'new').json()
    assert two['capture_now_ns'] == 14_500_000_000
    third = {'X-Moss-Capture-Instance': 'third'}
    for lane in ('system', 'microphone'):
        cursor = two['lanes'][lane]
        assert client.post(base + '/frames', json=bench.frame(lane, 9, 14.5, cursor['resume_device_epoch'], True), headers=third).status_code == 200
    assert client.post(base + '/stop', json={'deadline': 20}, headers=third).status_code == 200
    document = bench.wait_meeting(client, sid, 'completed')['transcript']
    assert document['capture_interruptions'] == [
        {'start_sample': 64000, 'end_sample': 144000},
        {'start_sample': 152000, 'end_sample': 232000}]


def test_stop_handoff_prevents_resume_while_raw_drain_pending(live):
    import asyncio
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    release = asyncio.Event()
    async def held_drain(deadline):
        await release.wait()
        return True
    engines[0].drain_tail = held_drain
    stopped = client.post(base + '/stop', json={'deadline': .01}, headers=old)
    assert stopped.status_code == 202
    assert resume(client, base).status_code == 409
    assert st.live_helper_failures.snapshot(sid) is None
    clock.now += 125 * bench.NS
    client.portal.call(timer.scheduled[-1][1].fire)
    client.portal.call(release.set)
    assert bench.wait_meeting(client, sid, 'completed')['status'] == 'completed'


def test_new_writer_cached_ack_does_not_close_pending_gap(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += 5 * bench.NS
    assert resume(client, base).status_code == 200
    new = {'X-Moss-Capture-Instance': 'new'}
    # Ingress discards the payload of an acknowledged sequence.
    r = client.post(base + '/frames', json=bench.frame('system', 0, 9, 1, True), headers=new)
    assert r.status_code == 200
    snapshot = client.get(base + '/snapshot').json()
    assert snapshot['snapshot']['session']['capture_interruptions'] == []
    assert snapshot['snapshot']['session']['sample_rate'] == bench.RATE
    document = client.get(f'/api/meetings/{sid}').json()['transcript']
    assert document['capture_interruptions'] == []
    assert document['sample_rate'] == bench.RATE


def test_early_resume_translates_nonzero_capture_origin_before_first_mix(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    clock.now += 500_000_000
    assert client.post(base + '/frames', json=bench.frame('system', 0, 7), headers=old).status_code == 200
    clock.now += 5 * bench.NS
    state = resume(client, base).json()
    assert state['capture_now_ns'] == 12_500_000_000
    assert state['interruption']['start_sample'] == 8000
    new = {'X-Moss-Capture-Instance': 'new'}
    for lane in ('system', 'microphone'):
        cursor = state['lanes'][lane]
        assert client.post(base + '/frames', headers=new,
            json=bench.frame(lane, cursor['next_sequence'], 12.5, cursor['resume_device_epoch'], True)).status_code == 200
    assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
    doc = bench.wait_meeting(client, sid, 'completed')['transcript']
    assert doc['capture_interruptions'] == [{'start_sample': 8000, 'end_sample': 88000}]


def test_resume_before_any_accepted_frame_is_late_start(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    clock.now += 5 * bench.NS
    response = resume(client, base, automatic=True)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['mixed_samples'] == 0
    assert all(cursor['next_sequence'] == 0 for cursor in state['lanes'].values())
    new = {'X-Moss-Capture-Instance': 'new'}
    for lane in ('system', 'microphone'):
        cursor = state['lanes'][lane]
        assert client.post(base + '/frames', headers=new,
            json=bench.frame(lane, 0, 5, cursor['resume_device_epoch'], True)).status_code == 200
    assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
    meeting = bench.wait_meeting(client, sid, 'completed')
    document = meeting['transcript']
    assert document.get('capture_interruptions', []) == []
    assert client.get(base + '/snapshot').json()['snapshot']['session'].get('capture_interruptions', []) == []
    assert state['interruption'] is None
    assert [(row['start'], row['end']) for row in document['segments']] == [(0, .5)]
    archives = list((st.resume_evidence_root / 'meetings').glob('**/audio.mp3'))
    assert len(archives) == 1
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(archives[0]),
        '-f', 's16le', '-ac', '1', '-ar', str(bench.RATE), '-'])
    assert len(pcm) // 2 == bench.RATE // 2
    assert engines[0].audio_blocks == [[0, bench.RATE // 2]]


@pytest.mark.parametrize('original_lane', ['system', 'microphone'])
def test_resume_with_one_accepted_lane_before_first_mix_keeps_gap(live, original_lane):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    clock.now += 500_000_000
    assert client.post(base + '/frames', json=bench.frame(original_lane, 0, 7), headers=old).status_code == 200
    clock.now += 5 * bench.NS
    state = resume(client, base, automatic=True).json()
    assert state['mixed_samples'] == 0
    assert state['interruption'] == {'start_sample': 8000, 'end_sample': None}
    new = {'X-Moss-Capture-Instance': 'new'}
    for lane in ('system', 'microphone'):
        cursor = state['lanes'][lane]
        assert client.post(base + '/frames', headers=new,
            json=bench.frame(lane, cursor['next_sequence'], 12.5, cursor['resume_device_epoch'], True)).status_code == 200
    assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
    document = bench.wait_meeting(client, sid, 'completed')['transcript']
    assert document['capture_interruptions'] == [{'start_sample': 8000, 'end_sample': 88000}]
    archives = list((st.resume_evidence_root / 'meetings').glob('**/audio.mp3'))
    assert len(archives) == 1
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(archives[0]),
        '-f', 's16le', '-ac', '1', '-ar', str(bench.RATE), '-'])
    assert len(pcm) // 2 == 6 * bench.RATE


def test_resume_then_stop_without_new_audio_omits_open_gap(live):
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    clock.now += 5 * bench.NS
    state = resume(client, base, automatic=True).json()
    assert state['interruption'] == {'start_sample': 4 * bench.RATE, 'end_sample': None}
    assert client.post(base + '/stop', json={'deadline': 20},
        headers={'X-Moss-Capture-Instance': 'new'}).status_code == 200
    document = bench.wait_meeting(client, sid, 'completed')['transcript']
    assert document['capture_interruptions'] == []
    archives = list((st.resume_evidence_root / 'meetings').glob('**/audio.mp3'))
    assert len(archives) == 1
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(archives[0]),
        '-f', 's16le', '-ac', '1', '-ar', str(bench.RATE), '-'])
    assert len(pcm) // 2 == 4 * bench.RATE


def test_headerless_stale_bundle_never_resumes_normal_meeting(tmp_path):
    app, cookies, engines = bench.build_app(tmp_path / 'stale')
    with TestClient(app, base_url='https://moss.test') as client:
        bench.session(client, cookies['a'])
        sid = client.post('/api/live/sessions', json={'engine_settings': bench.SETTINGS}).json()['id']
        base = f'/api/live/sessions/{sid}'
        assert client.post(base + '/heartbeat', json=bench.hb('stale-bundle')).status_code == 200
        for i in range(8):
            for lane in ('system', 'microphone'):
                assert client.post(base + '/frames', json=bench.frame(lane, i, i * .5)).status_code == 200
        assert client.post(base + '/stop', json={'deadline': 20}).status_code == 200
        meeting = bench.wait_meeting(client, sid, 'completed')
        assert 'capture_interruptions' not in meeting['transcript']
        archives = list((tmp_path / 'stale/meetings').glob('**/audio.mp3'))
        assert len(archives) == 1
        pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(archives[0]), '-f', 's16le', '-ac', '1', '-ar', '16000', '-'])
        assert len(pcm) == 4 * 16000 * 2


def test_saved_interruption_survives_full_server_restart(tmp_path):
    root = tmp_path / 'restart'
    app, cookies, engines = bench.build_app(root)
    clock = bench.Clock()
    with TestClient(app, base_url='https://moss.test') as client:
        bench.session(client, cookies['a'])
        st = app.state
        st.live_helper_presence._monotonic_ns = clock
        st.live_helper_failures._monotonic_ns = clock
        st.live_helper_failures._timer = bench.FakeTimer()
        sid = client.post('/api/live/sessions', json={'engine_settings': bench.SETTINGS}).json()['id']
        base = f'/api/live/sessions/{sid}'
        old = {'X-Moss-Capture-Instance': 'old'}
        assert client.post(base + '/heartbeat', json=bench.hb('old'), headers=old).status_code == 200
        for i in range(2):
            clock.now += 500_000_000
            for lane in ('system', 'microphone'):
                assert client.post(base + '/frames', json=bench.frame(lane, i, i * .5), headers=old).status_code == 200
        clock.now += 5 * bench.NS
        assert resume(client, base).status_code == 200
        new = {'X-Moss-Capture-Instance': 'new'}
        for lane in ('system', 'microphone'):
            assert client.post(base + '/frames', json=bench.frame(lane, 2, 6, 1, True), headers=new).status_code == 200
        assert client.post(base + '/stop', json={'deadline': 20}, headers=new).status_code == 200
        saved = bench.wait_meeting(client, sid, 'completed')['transcript']
    restarted = bench.make_app(root / 'meeting.sqlite', live_runtime_factory=lambda: bench.GeminiLiveRuntime(
        descriptor=bench.descriptor(), tape_storage_root=root / 'restart-tapes',
        engine_factory=lambda _sid, publish, _usage, _settings: bench.OfflineEngine(publish)))
    with TestClient(restarted, base_url='https://moss.test') as client:
        bench.session(client, cookies['a'])
        assert client.get(f'/api/meetings/{sid}').json()['transcript'] == saved
        assert client.get('/api/meetings').json()['meetings'][0]['id'] == sid
        assert saved['capture_interruptions'] == [{'start_sample': 16000, 'end_sample': 96000}]
        assert saved['sample_rate'] == bench.RATE
        assert resume(client, base).status_code in {404, 409}
        bench.session(client, cookies['b'])
        assert client.get(f'/api/meetings/{sid}').status_code == 404


@pytest.mark.parametrize('lane', ['system', 'microphone'])
@pytest.mark.parametrize('resumed', [False, True])
def test_stalled_frame_body_does_not_block_peer_lane_or_heartbeat(live, lane, resumed):
    import asyncio
    import httpx
    client, st, cookies, engines, clock, timer, sid, base, old = live
    if resumed:
        state = resume(client, base).json()
        headers = {'X-Moss-Capture-Instance': 'new'}
        heartbeat = bench.hb('new', state['heartbeat_next_sequence'])
        heartbeat['sent_monotonic_ns'] = state['heartbeat_next_monotonic_ns']
    else:
        headers, heartbeat = old, bench.hb('old', 1)
    epoch = int(resumed)
    async def exercise():
        stalled, release = asyncio.Event(), asyncio.Event()
        body = json.dumps(bench.frame(lane, 0, 0, epoch, resumed)).encode()
        async def upload():
            yield body[:len(body) // 2]
            stalled.set()
            await release.wait()
            yield body[len(body) // 2:]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                base_url='https://moss.test', cookies=client.cookies) as wire:
            slow = asyncio.create_task(wire.post(base + '/frames', content=upload(),
                headers={**headers, 'Content-Type': 'application/json'}))
            try:
                await asyncio.wait_for(stalled.wait(), timeout=1)
                peer = 'microphone' if lane == 'system' else 'system'
                accepted = await asyncio.wait_for(asyncio.gather(
                    wire.post(base + '/frames', json=bench.frame(peer, 0, 0, epoch, resumed), headers=headers),
                    wire.post(base + '/heartbeat', json=heartbeat, headers=headers)), timeout=1)
                assert [r.status_code for r in accepted] == [200, 200]
                assert not slow.done() and not release.is_set()
            finally:
                release.set()
                response = await asyncio.wait_for(slow, timeout=2)
            assert response.status_code == 200, response.text
    client.portal.call(exercise)


@pytest.mark.parametrize('ending', ['stop', 'abort', 'expiry'])
def test_capture_writer_removed_at_capture_end(live, ending):
    import inspect
    client, st, cookies, engines, clock, timer, sid, base, old = live
    # Observe the existing registry, including on the unmodified red candidate.
    route = next(r for r in client.app.routes if getattr(r, 'path', '') == '/api/live/sessions/{session_id}/frames')
    writers = inspect.getclosurevars(route.dependant.dependencies[0].call).nonlocals['capture_writers']
    assert sid in writers
    prefix(live)
    if ending == 'expiry':
        clock.now = st.live_helper_failures.snapshot(sid).deadline_monotonic_ns
        client.portal.call(timer.scheduled[-1][1].fire)
    else:
        payload = {'deadline': 20} if ending == 'stop' else {'reason': 'test capture end'}
        assert client.post(base + '/' + ending, json=payload, headers=old).status_code == 200
    assert bench.wait_meeting(client, sid, 'completed' if ending == 'stop' else 'interrupted')
    assert sid not in writers


def test_writer_replaced_while_body_uploading_is_fenced_at_mutation(live):
    import asyncio
    import httpx
    client, st, cookies, engines, clock, timer, sid, base, old = live
    async def exercise():
        stalled, release = asyncio.Event(), asyncio.Event()
        body = json.dumps(bench.frame('system', 0, 0)).encode()
        async def upload():
            yield body[:len(body) // 2]
            stalled.set()
            await release.wait()
            yield body[len(body) // 2:]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                base_url='https://moss.test', cookies=client.cookies) as wire:
            slow = asyncio.create_task(wire.post(base + '/frames', content=upload(), headers=old))
            try:
                await asyncio.wait_for(stalled.wait(), timeout=1)
                adopted = await asyncio.wait_for(wire.post(base + '/resume', json={
                    'expected_instance_id': 'old', 'instance_id': 'new', 'automatic': False}), timeout=1)
                assert adopted.status_code == 200
            finally:
                release.set()
                response = await asyncio.wait_for(slow, timeout=2)
            assert response.status_code == 409
            assert response.json()['code'] == 'capture_replaced'
            assert st.live_v2_sessions.get(sid).resume_lanes()['system']['next_sequence'] == 0
    client.portal.call(exercise)


@pytest.mark.parametrize('ending', ['stop', 'abort', 'expiry'])
def test_delayed_heartbeat_cannot_recreate_capture_after_teardown(live, ending):
    import asyncio
    import httpx
    client, st, cookies, engines, clock, timer, sid, base, old = live
    prefix(live)
    async def exercise():
        stalled, release = asyncio.Event(), asyncio.Event()
        body = json.dumps(bench.hb('old', 2)).encode()
        async def upload():
            yield body[:len(body) // 2]
            stalled.set()
            await release.wait()
            yield body[len(body) // 2:]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                base_url='https://moss.test', cookies=client.cookies) as wire:
            slow = asyncio.create_task(wire.post(base + '/heartbeat', content=upload(), headers=old))
            try:
                await asyncio.wait_for(stalled.wait(), timeout=1)
                if ending == 'expiry':
                    clock.now = st.live_helper_failures.snapshot(sid).deadline_monotonic_ns
                    timer.scheduled[-1][1].fire()
                else:
                    payload = {'deadline': 20} if ending == 'stop' else {'reason': 'end during upload'}
                    ended = await asyncio.wait_for(wire.post(base + '/' + ending,
                        json=payload, headers=old), timeout=2)
                    assert ended.status_code == 200
                async def wait_terminal():
                    while (await wire.get(f'/api/meetings/{sid}')).json()['status'] == 'active':
                        await asyncio.sleep(.01)
                await asyncio.wait_for(wait_terminal(), timeout=2)
                assert st.live_helper_presence.snapshot(sid) is None
            finally:
                release.set()
                response = await asyncio.wait_for(slow, timeout=2)
            assert response.status_code == 409
            assert response.json()['code'] == 'live_session_terminal'
            assert st.live_helper_presence.snapshot(sid) is None
            assert st.live_helper_failures.snapshot(sid) is None
    client.portal.call(exercise)
