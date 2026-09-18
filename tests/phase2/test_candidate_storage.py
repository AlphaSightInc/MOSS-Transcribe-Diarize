from pathlib import Path
import json
import os
import shutil

import pytest

from moss_transcribe_diarize import candidate_storage as storage


@pytest.mark.parametrize('root,windows,refused', [(20,10,False),(19,10,True),(20,9,True),(20,None,False)])
def test_space_thresholds_and_unavailable_windows(monkeypatch, root, windows, refused):
    monkeypatch.setattr(storage.shutil, 'disk_usage', lambda p: shutil._ntuple_diskusage(100*10**9,0,root*10**9))
    monkeypatch.setattr(storage, 'is_wsl', lambda: True)
    monkeypatch.setattr(storage, 'windows_free_bytes', lambda: None if windows is None else windows*10**9)
    if refused:
        with pytest.raises(storage.StorageRefused, match='insufficient_disk_space'):
            storage.check_space()
    else:
        rows=storage.check_space()
        assert rows[-1]['status']==('unavailable' if windows is None else 'ok')


def test_space_override_and_non_wsl(monkeypatch):
    monkeypatch.setenv('MOSS_MIN_ROOT_FREE_GB','1')
    monkeypatch.setattr(storage.shutil,'disk_usage',lambda p: shutil._ntuple_diskusage(2*10**9,0,10**9))
    monkeypatch.setattr(storage,'is_wsl',lambda:False)
    assert storage.check_space()[0]['status']=='ok'


def directory(path, age, now=200000):
    path.mkdir(parents=True)
    (path/'data').write_bytes(b'x'*1024)
    os.utime(path,(now-age,now-age))
    return path


def test_retention_survivors_and_dry_run(tmp_path):
    share=tmp_path/'.local/share/moss-transcribe-diarize'
    state=tmp_path/'.local/state/moss-transcribe-diarize'
    runtime=[directory(share/'account-runtimes'/str(n),100+n) for n in range(5)]
    (share/'account-current').symlink_to(runtime[4])
    attempts=[]
    for n in range(5):
        p=directory(state/'cutover-attempts'/str(n),100+n)
        (p/'result.json').write_text(json.dumps({'terminal':'restored'}))
        os.utime(p,(200000-100-n,)*2)
        attempts.append(p)
    current=attempts[3]
    (current/'result.json').unlink()
    (current/'candidate-manifest.json').write_text(json.dumps({'release':str(runtime[3])}))
    stale=directory(share/'candidate-checkouts'/'stale',90000)
    fresh=directory(share/'candidate-checkouts'/'fresh',100)
    protected_checkout=directory(share/'candidate-checkouts'/'4',90000)
    workspace=directory(state/'qualification-workspaces'/'old',90000)
    outside=directory(tmp_path/'outside',90000)
    (share/'candidate-checkouts'/'escape').symlink_to(outside, target_is_directory=True)
    before=sorted(str(p) for p in tmp_path.rglob('*'))
    plan=storage.prune(tmp_path,keep=2,now=200000,dry_run=True)
    assert sorted(str(p) for p in tmp_path.rglob('*'))==before
    assert {Path(r['path']).name for r in plan if r['kind']=='runtime'}=={'2'}
    result=storage.prune(tmp_path,keep=2,now=200000)
    assert result and all(r['bytes']>0 for r in result)
    assert not runtime[2].exists() and not attempts[4].exists()
    assert all(p.exists() for p in [*runtime[:2],runtime[3],runtime[4],current,fresh,protected_checkout,outside])
    assert not stale.exists() and not workspace.exists()


def test_parent_symlink_never_pruned(tmp_path):
    outside=directory(tmp_path/'outside'/'old',90000)
    parent=tmp_path/'.local/share/moss-transcribe-diarize'
    parent.mkdir(parents=True)
    (parent/'candidate-checkouts').symlink_to(outside.parent,target_is_directory=True)
    storage.prune(tmp_path,now=200000)
    assert outside.exists()


def test_windows_mount_and_powershell_fallback(monkeypatch):
    monkeypatch.setattr(storage.os.path, 'ismount', lambda p: True)
    monkeypatch.setattr(storage.shutil,'disk_usage',lambda p: shutil._ntuple_diskusage(0,0,12*10**9))
    assert storage.windows_free_bytes()==12*10**9
    monkeypatch.setattr(storage.os.path,'ismount',lambda p:False)
    monkeypatch.setattr(storage.subprocess,'run',lambda *a,**k: storage.subprocess.CompletedProcess(a,0,'11000000000\r\n',''))
    assert storage.windows_free_bytes()==11*10**9
    def unavailable(*a,**k): raise FileNotFoundError()
    monkeypatch.setattr(storage.subprocess,'run',unavailable)
    assert storage.windows_free_bytes() is None


@pytest.mark.parametrize('value',['0','-1','nan','inf','bad'])
def test_invalid_threshold_refuses(monkeypatch,value):
    monkeypatch.setenv('MOSS_MIN_ROOT_FREE_GB',value)
    with pytest.raises(storage.StorageRefused): storage.check_space()


def test_readonly_runtime_removed_without_following_internal_symlink(tmp_path):
    share=tmp_path/'.local/share/moss-transcribe-diarize'
    newest=directory(share/'account-runtimes'/'new',0)
    old=directory(share/'account-runtimes'/'old',100)
    outside=directory(tmp_path/'outside',200)
    (old/'escape').symlink_to(outside,target_is_directory=True)
    os.utime(old,(199900,)*2)
    (old/'data').chmod(0o444)
    old.chmod(0o555)
    storage.prune(tmp_path,keep=1,now=200000)
    assert newest.exists() and outside.exists() and not old.exists()


def test_explicit_current_protection_and_safe_stopped(tmp_path):
    share=tmp_path/'.local/share/moss-transcribe-diarize'
    state=tmp_path/'.local/state/moss-transcribe-diarize'
    directory(share/'account-runtimes'/'new',0)
    old=directory(share/'account-runtimes'/'old',100)
    current=directory(share/'staging'/'current',90000)
    broken=directory(state/'cutover-attempts'/'unsafe',90000)
    (broken/'result.json').write_text('{"terminal":"SAFE_STOPPED"}')
    (broken/'candidate-manifest.json').write_text(json.dumps({'release':str(old)}))
    storage.prune(tmp_path,keep=1,now=200000,protect=(current,))
    assert all(p.exists() for p in (current,old,broken))


def test_prune_cli_refuses_live_cutover_lock(tmp_path):
    import fcntl
    import subprocess
    import sys
    lock=tmp_path/'.local/state/moss-transcribe-diarize/phase2-cutover.lock'
    lock.parent.mkdir(parents=True)
    with lock.open('w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=subprocess.run([sys.executable,storage.__file__,'--prune','--home',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==2 and 'cutover_or_staging_in_progress' in result.stdout


def test_staging_refuses_before_wheel_or_build(tmp_path):
    import subprocess
    env=dict(os.environ,MOSS_MIN_ROOT_FREE_GB='1000000000')
    env.pop('MOSS_CANDIDATE_WHEEL',None)
    result=subprocess.run(['bash','ops/stage-account-candidate.sh'],env=env,capture_output=True,text=True)
    assert result.returncode==2 and 'insufficient_disk_space' in result.stdout
    assert 'MOSS_CANDIDATE_WHEEL' not in result.stderr


@pytest.mark.parametrize("flag", [True, False])
def test_staging_dry_run_deletes_nothing(tmp_path, flag):
    import subprocess
    share=tmp_path/'.local/share/moss-transcribe-diarize'
    victim=directory(share/'staging'/'old',2*storage.DAY,now=storage.time.time())
    # Keep fake home outside the script's protected checkout, including when pytest's
    # basetemp is inside the real checkout. Exercise unmodified production scripts.
    import shutil
    checkout=tmp_path/'checkout'
    (checkout/'ops').mkdir(parents=True)
    (checkout/'moss_transcribe_diarize').mkdir()
    for name in ('stage-account-candidate.sh','moss-ops-lib.sh'):
        shutil.copyfile(Path('ops')/name,checkout/'ops'/name)
    shutil.copyfile(storage.__file__,checkout/'moss_transcribe_diarize/candidate_storage.py')
    result=subprocess.run(['bash',str(checkout/'ops/stage-account-candidate.sh')] + (['--dry-run'] if flag else []),
                          env=dict(os.environ,HOME=str(tmp_path),MOSS_TOOL_DRY_RUN='0' if flag else '1'),capture_output=True,text=True)
    assert result.returncode==0 and 'would_remove' in result.stdout
    assert victim.exists() and (victim/'data').read_bytes()==b'x'*1024
