"""Regression checks: a list the tester runs again on every new build, pass or fail, in bugs/.checks.json.
{'checks': [{'id': 1, 'text': ...}], 'runs': {'<game version>': {'<check id>': 'pass' | 'fail'}}, 'last_build': ...}
"""
import json
from pathlib import Path

FILE = '.checks.json'
MARK = {'pass': '✅', 'fail': '❌'}


def load(root):
    try:
        return json.loads((Path(root) / FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'checks': [], 'runs': {}}


def save(root, data):
    Path(root).mkdir(parents=True, exist_ok=True)
    (Path(root) / FILE).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def add(data, text):
    text = ' '.join(str(text).split())[:200]
    if not text or any(c['text'] == text for c in data['checks']):
        return None
    check = {'id': max((c['id'] for c in data['checks']), default=0) + 1, 'text': text}
    data['checks'].append(check)
    return check


def remove(data, check_id):
    data['checks'] = [c for c in data['checks'] if c['id'] != check_id]


def result(data, build, check_id, res):
    """res: 'pass', 'fail', or None to clear it."""
    run = data['runs'].setdefault(build, {})
    if res:
        run[str(check_id)] = res
    else:
        run.pop(str(check_id), None)
    data['last_build'] = build


def report(data, build):
    """A short build report to paste in Discord."""
    run = data['runs'].get(build, {})
    done = [(c, run[str(c['id'])]) for c in data['checks'] if str(c['id']) in run]
    fails = [c['text'] for c, r in done if r == 'fail']
    lines = [f"Build {build}: {sum(r == 'pass' for _, r in done)} passed, {len(fails)} failed, "
             f"{len(data['checks']) - len(done)} not checked"]
    lines += [f"❌ {t}" for t in fails]
    return '\n'.join(lines)
