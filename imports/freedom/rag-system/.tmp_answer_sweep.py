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
    with urlopen(url, timeout=90) as resp:
        payload=json.loads(resp.read().decode('utf-8'))
    results.append({
        'id': r.get('id'),
        'refused': bool(payload.get('refused')),
        'answer_chars': len(str(payload.get('answer_text') or '')),
        'llm_error': payload.get('llm_error'),
        'strategy': payload.get('answer_strategy'),
        'boost_applied': payload.get('relevancy_boost_applied'),
    })

zero=sum(1 for x in results if x['answer_chars']==0)
ref=sum(1 for x in results if x['refused'])
print('queries',len(results))
print('zero_answers',zero)
print('refused',ref)
print('nonzero',len(results)-zero)
print('sample',results[:5])
print('strategies', {k: sum(1 for x in results if x['strategy']==k) for k in sorted(set(x['strategy'] for x in results))})
