"""Presenter script contracts; fake curl returns protocol outcomes without host calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/demo-precheck.sh'
SHA = 'a' * 40


@pytest.mark.parametrize('case,failed', [
    ('okay', None), ('primary_only', None), ('openrouter', None),
    ('tls', 'trusted host'), ('identity', 'candidate identity'),
    ('models', 'relay models'), ('bootstrap', 'bootstrap'),
    ('empty', 'rtx4090'), ('timeout', 'macstudio'), ('malformed', 'rtx4090'),
])
def test_precheck_go_requires_all_checks_and_keeps_protocol_bounds(tmp_path,case,failed):
    curl=tmp_path/'curl'
    curl.write_text('#!'+sys.executable+'\n'+r'''
import json, os, sys
from pathlib import Path
args=sys.argv[1:]; url=args[-1]; case=os.environ['PRECHECK_CASE']
assert args[0]=='--disable' and '--insecure' not in args and '-k' not in args
assert args[args.index('--max-time')+1]=='30'
body=Path(args[args.index('--output')+1]);headers=Path(args[args.index('--dump-header')+1])
with open(os.environ['PRECHECK_LOG'],'a') as log: log.write(url+'\n')
status=200; result={}; sha='b'*40 if case=='identity' else 'a'*40
headers.write_text('HTTP/1.1 200 OK\r\nX-MOSS-Candidate-SHA: '+sha+'\r\n')
if url.endswith('/bootstrap'):
    assert args[args.index('--request')+1]=='POST'
    Path(args[args.index('--cookie-jar')+1]).write_text('test cookie')
    if case=='bootstrap': status=503
elif url.endswith('/models'):
    assert Path(args[args.index('--cookie')+1]).read_text()=='test cookie'
    result={'data':[{'upstream':'macstudio','id':'qwen/qwen3.6-35b-a3b'}, {'upstream':'rtx4090','id':'qwen38-27b-mtp'}]}
    if case=='primary_only': result={'data':[{'upstream':'macstudio','id':'qwen/qwen3.6-35b-a3b'}]}
    if case=='models': result={'data':[]}
elif url.endswith('/chat/completions'):
    request=json.loads(sys.stdin.read())
    assert request['max_tokens']==16 and request['stream'] is False
    if 'openrouter.ai' in url:
        assert 'Authorization: Bearer test-openrouter-key' in args
        assert request['response_format']=={'type':'json_object'}
    else:
        assert request['chat_template_kwargs']=={'enable_thinking':False}
    if case=='timeout' and 'macstudio.' in url: sys.exit(28)
    result={'choices':[{'message':{'content':'' if case=='empty' and 'rtx4090.' in url else 'ready'}}]}
    if case=='malformed' and 'rtx4090.' in url:
        body.write_text('not json');print('200\n0.012');sys.exit(0)
elif case=='tls': sys.exit(60)
body.write_text(json.dumps(result))
print(str(status)+'\n0.012')
''')
    curl.chmod(0o700)
    log=tmp_path/'requests.txt'
    result=subprocess.run(['bash',str(SCRIPT),SHA],env={**os.environ,'PATH':str(tmp_path)+os.pathsep+os.environ['PATH'],
        'PRECHECK_CASE':case,'PRECHECK_LOG':str(log),
        'MOSS_DEMO_RTX4090_BASE':'' if case=='primary_only' else 'http://ga0-rtx4090.tailnet.aisight.us:1235/v1',
        'MOSS_DEMO_OPENROUTER_API_KEY':'test-openrouter-key' if case=='openrouter' else ''},text=True,capture_output=True)
    final=result.stdout.splitlines()[-1]
    assert result.stderr==''
    assert result.returncode==(0 if failed is None else 1)
    assert final=='GO' if failed is None else final.startswith('NO-GO:') and failed in final
    urls=log.read_text().splitlines()
    assert any('macstudio.' in url and url.endswith('/chat/completions') for url in urls)
    assert any('rtx4090.' in url for url in urls)==(case!='primary_only')
    assert any('openrouter.ai' in url for url in urls)==(case=='openrouter')
    assert 'test-openrouter-key' not in result.stdout + result.stderr
    assert urls[-1].endswith('/chat/completions')
    assert ' s' in result.stdout


def test_bad_sha_is_explicit_no_go_without_curl():
    result=subprocess.run(['bash',str(SCRIPT),'short'],text=True,capture_output=True)
    assert result.returncode==1 and result.stdout.splitlines()[-1].startswith('NO-GO:')
    assert result.stderr==''
