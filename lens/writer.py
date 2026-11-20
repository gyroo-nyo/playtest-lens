"""AI-written reports with a local model (Ollama). Nothing leaves the Mac: cloud models are skipped.

The model gets only facts Lens already has (kind, note, the scoreboard, the named taps, the matched
log lines, device) and returns a title, steps, expected and actual. Lens writes the Markdown around
it, so the attachments and the device table always stay right.
"""
import json
import urllib.request

OLLAMA = 'http://127.0.0.1:11434'
PREFER = ('qwen3:8b', 'qwen2.5:7b', 'llama3.1:8b', 'gemma3:4b', 'qwen2.5-coder:7b')


def models():
    """Installed local models, preferred ones first; [] when Ollama isn't running."""
    try:
        with urllib.request.urlopen(f'{OLLAMA}/api/tags', timeout=2) as r:
            found = json.load(r).get('models', [])
    except (OSError, ValueError):
        return None
    # "-cloud" models run on someone else's server; size 0 means listed but not downloaded
    local = [m['name'] for m in found if 'cloud' not in m['name'] and m.get('size', 1) > 0]
    return [p for p in PREFER if p in local] + [n for n in local if n not in PREFER]


def model():
    return next(iter(models()), None)


def facts(kind_label, ev_title, note, meta, desc, log_lines):
    did = desc.get('did', []) if desc else []
    return {
        'kind': kind_label, 'detected_as': ev_title, 'tester_note': note or '',
        'on_screen_at_the_bug': (desc or {}).get('situation', ''),
        'tester_pressed_last_15s': (desc or {}).get('summary', ''),
        'device': f"{meta.get('model')} (Android {meta.get('android')})", 'game': f"{meta.get('package')} {meta.get('game_version')}",
        'matched_log_lines': log_lines[:8],
    }


PROMPT = """You write bug reports for a mobile game studio. Rewrite the tester's note as a clear
report. Rules:
- Use ONLY these facts. Never invent screens, features, causes or consequences.
- It is a crash only if "kind" is Crash. Otherwise do not say crash, freeze or hang.
- The actions are button labels as printed on screen. Do not guess what a button does.
- Steps: 2 to 5 short steps a developer can follow, e.g. "Get to 2nd down and 11 in Q2",
  "Press DIVE and SWITCH repeatedly". Group repeated presses; never list taps one by one.

Facts (JSON):
{facts}

Reply with JSON only:
{{"title": "under 80 characters, what went wrong",
  "severity": "critical | major | minor",
  "steps": ["short imperative steps that lead to the bug, from the actions and the situation"],
  "actual": "one or two sentences",
  "expected": "one sentence"}}"""


def draft(f, timeout=180):
    """{'title', 'severity', 'steps', 'actual', 'expected', 'model'} from the first local model that
    answers (a model can be listed but missing its files), or None."""
    for name in models():
        out = ask(f, name, timeout)
        if out:
            return out
    return None


def ask(f, name, timeout):
    body = json.dumps({'model': name, 'prompt': PROMPT.format(facts=json.dumps(f, ensure_ascii=False, indent=1)),
                       'format': 'json', 'stream': False, 'think': False, 'options': {'temperature': 0.2}}).encode()
    req = urllib.request.Request(f'{OLLAMA}/api/generate', body, {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(json.load(r)['response'])
    except (OSError, ValueError, KeyError):
        return None
    if not isinstance(out, dict) or not out.get('title'):
        return None
    out['steps'] = [str(s) for s in out.get('steps') or [] if str(s).strip()]
    out['model'] = name
    return out
