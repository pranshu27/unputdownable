import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

rows=[]
for raw in Path('eval/golden_answer_eval.jsonl').read_text(encoding='utf-8').splitlines():
    line=raw.strip()
    if not line or line.startswith('#'):
        continue
    rows.append(json.loads(line))

base='http://localhost:8000/answer'
results=[]
for r in rows:
    params={
        'q':r['query'],
        'k':str(int(r.get('k') or 6)),
        'mode':str(r.get('mode') or 'hybrid'),
        'rerank':'false',
        'llm':'true',
        'use_graph':'true',
        'relevancy_boost':'true',
    }
    url=base+'?'+urlencode(params)
    try:
        with urlopen(url, timeout=60) as resp:
            payload=json.loads(resp.read().decode('utf-8'))
        results.append({
            'id': r.get('id'),
            'ok': True,
            'refused': bool(payload.get('refused')),
            'answer_chars': len(str(payload.get('answer_text') or '')),
            'llm_error': str(payload.get('llm_error') or ''),
            'strategy': str(payload.get('answer_strategy') or ''),
            'boost_applied': bool(payload.get('relevancy_boost_applied')),
        })
    except Exception as exc:
        results.append({
            'id': r.get('id'),
            'ok': False,
            'error': str(exc),
            'refused': None,
            'answer_chars': 0,
            'llm_error': 'request_failed',
            'strategy': '',
            'boost_applied': False,
        })

out=Path('eval/answer_sweep_latest.json')
out.write_text(json.dumps(results, indent=2), encoding='utf-8')

zero=sum(1 for x in results if x['ok'] and x['answer_chars']==0)
ref=sum(1 for x in results if x['ok'] and x['refused'])
failed=sum(1 for x in results if not x['ok'])
print('queries',len(results))
print('zero_answers',zero)
print('refused',ref)
print('failed_requests',failed)
print('nonzero',sum(1 for x in results if x['ok'] and x['answer_chars']>0))
print('output',str(out))
