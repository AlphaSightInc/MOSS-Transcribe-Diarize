"""Opt-in replay bench; only numeric/status measurements retained; request input stays private.

PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/thinking_request_probe.py --request /tmp/private-relay-request.json --output /tmp/moss-thinking-replay --stages relay baseline disabled disabled2048 --browser-state /tmp/moss-e2e-20260911/browser-state.json
Original frontend omits max_tokens; baseline applies the old relay default (1024).
Each stage changes only the named variable. Fresh output directory required.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time

import httpx

MODELS = [
    ('macstudio', 'qwen/qwen3.6-35b-a3b', 'http://macstudio.tailnet.aisight.us:1234/v1'),
    ('rtx4090', 'qwen38-27b-mtp', 'http://ga0-rtx4090.tailnet.aisight.us:1235/v1'),
]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


async def probe(args, name, model, url, stage):
    body = {**json.loads(args.request.read_text()), 'model': model}
    cookies = {}
    if stage == 'relay':
        state = json.loads(args.browser_state.read_text())
        cookies = {c['name']: c['value'] for c in state['cookies'] if c['domain'] == '127.0.0.1'}
        url = 'https://127.0.0.1:17861/api/llm'
    else:
        body.update(stream=False, max_tokens=2048 if stage == 'disabled2048' else body.get('max_tokens', 1024))
        if stage.startswith('disabled'):
            body['chat_template_kwargs'] = {'enable_thinking': False}
    label = f'{name}-{stage}'
    start = time.monotonic()
    async with httpx.AsyncClient(verify=False, trust_env=False, timeout=190, cookies=cookies) as client:
        response = await client.post(url + '/chat/completions', json=body, headers={'Origin': 'https://127.0.0.1:17861'})
    raw = response.json()
    choice = (raw.get('choices') or [{}])[0]
    message = choice.get('message', {})
    content = message.get('content') or ''
    reasoning = message.get('reasoning_content') or ''
    try:
        summary = json.loads(content).get('summary')
    except (ValueError, AttributeError):
        summary = None
    result = {'case': label, 'status': response.status_code, 'seconds': round(time.monotonic() - start, 2),
              'content_chars': len(content), 'reasoning_chars': len(reasoning), 'summary_present': isinstance(summary, str) and bool(summary),
              'finished': choice.get('finish_reason') == 'stop', 'usage': {k:v for k,v in (raw.get('usage') or {}).items() if k in ('prompt_tokens','completion_tokens','total_tokens') and isinstance(v,int)}, 'failed': not response.is_success}
    write(args.output / f'{label}-metrics.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


async def run(args):
    for stage in args.stages:
        await asyncio.gather(*(probe(args, *model, stage) for model in MODELS))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stages', nargs='+', choices=['relay', 'baseline', 'disabled', 'disabled2048'], required=True)
    parser.add_argument('--browser-state', type=Path)
    args = parser.parse_args()
    if 'relay' in args.stages and args.browser_state is None:
        parser.error('--browser-state is required for authenticated relay replay')
    args.output.mkdir(parents=True, exist_ok=False)
    asyncio.run(run(args))
