"""Durable completion alone must not let the next capture skip Reset."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from tests.e2e.verify_workspace import Harness


class Page:
    def __init__(self, phase):
        self.phase=phase

    def locator(self, selector):
        assert selector=='[data-capture-phase]'
        return self

    async def get_attribute(self, name):
        assert name=='data-capture-phase'
        return self.phase


@pytest.mark.parametrize('session,history', [
    ({'status':'closed','finalization_status':'final'}, 'active'),
    ({'status':'active','finalization_status':'pending'}, 'completed'),
])
def test_waits_for_ui_terminal_after_durable_completion(tmp_path,session,history):
    async def run():
        harness=Harness(SimpleNamespace(output=str(tmp_path),base="https://fixture.test"))
        harness.page=Page('stopping'); harness.last_live_meeting='owned'; harness.row=14
        calls=[]
        async def api(path):
            calls.append(path)
            return {'body':{'snapshot':{'session':session}} if path.endswith('/snapshot') else {'status':history}}
        harness.api=api
        async def finish_ui():
            await asyncio.sleep(.02)
            harness.page.phase='terminal'
        task=asyncio.create_task(finish_ui())
        try:
            await harness.wait_before_reset(timeout=1)
            assert task.done()
            assert len(calls)>=4  # durable alone did not release setup
            evidence=json.loads((tmp_path/'row-14-before-reset.json').read_text())
            assert evidence['ready'] and evidence['phase']=='terminal'
        finally:
            await task
            harness.network.close()
    asyncio.run(run())


@pytest.mark.parametrize('phase,history', [('stopping','completed'),('terminal','active')])
def test_timeout_retains_reason_and_does_not_continue(tmp_path,phase,history):
    async def run():
        harness=Harness(SimpleNamespace(output=str(tmp_path),base="https://fixture.test"))
        harness.page=Page(phase); harness.last_live_meeting='owned'; harness.row=14
        async def api(path):
            return {'body':{'snapshot':{'session':{'status':'active','finalization_status':'pending'}}} if path.endswith('/snapshot') else {'status':history}}
        harness.api=api
        try:
            with pytest.raises(AssertionError,match='previous meeting did not reach durable completion and UI terminal before Reset'):
                await harness.wait_before_reset(timeout=.02)
            evidence=json.loads((tmp_path/'row-14-before-reset.json').read_text())
            assert not evidence['ready'] and evidence['meeting']=='owned'
            assert evidence['phase']==phase and evidence['history_status']==history
            assert evidence['reason_code']=='previous_meeting_not_ready'
            assert evidence['exception']=='TimeoutError'
        finally:
            harness.network.close()
    asyncio.run(run())
