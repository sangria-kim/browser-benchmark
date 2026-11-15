"""Build a dependency-free public dashboard from the repository's evidence."""
import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text())


def build(output):
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    ref = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() or 'detached'
    base = f'https://github.com/sangria-kim/browser-benchmark/blob/{sha}/'
    events = []
    ids = set()
    for path in sorted((ROOT / 'data/events').glob('*.json')):
        d = read_json(path)
        if d['event_id'] in ids:
            raise ValueError('Duplicate event: ' + d['event_id'])
        ids.add(d['event_id'])
        d['document_url'] = base + path.relative_to(ROOT).as_posix()
        events.append(d)
    # Resolve document links from actual event references, never guessed feature filenames.
    for path in (ROOT / 'features').glob('*/*.md'):
        body = path.read_text()
        for d in events:
            if d['event_id'] + '.json' in body:
                d['feature_url'] = base + path.relative_to(ROOT).as_posix()
                heading = re.search(r'^# (.+)$', body, re.MULTILINE)
                if heading:
                    d['feature_title'] = heading.group(1)
    for path in (ROOT / 'reports').glob('????-??-??.md'):
        body = path.read_text()
        for d in events:
            if d['event_id'] + '.json' in body:
                d.setdefault('reports', []).append({'date': path.stem, 'url': base + path.relative_to(ROOT).as_posix()})
    flags = []
    for path in sorted((ROOT / 'experiments/chrome').glob('*.md')):
        if path.name == 'README.md':
            continue
        body = path.read_text()
        history = []
        for line in body.splitlines():
            if re.match(r'\|\s*\d{4}-\d{2}-\d{2}', line):
                cells = [c.strip() for c in line.strip('|').split('|')]
                if len(cells) >= 4:
                    urls = re.findall(r'https://[^)\s]+', cells[-1])
                    history.append({'date': cells[0], 'action': cells[1], 'platform': cells[2], 'url': urls[0] if urls else None})
        dates = re.findall(r'20\d{2}-\d{2}-\d{2}', body)
        links = [{'label': m[0], 'url': m[1]} for m in re.findall(r'\[([^\]]+)\]\((https://[^)]+)\)', body)]
        related = [d['event_id'] for d in events if d['event_id'] + '.json' in body]
        default = re.search(r'소스 기본값:\s*([^\.\n]+)', body)
        expiry = re.search(r'만료 milestone[: ]+([^\.\n]+)', body)
        flags.append({'id': path.stem, 'body': body, 'history': history, 'date': max(dates, default=''),
                      'default_state': default.group(1).strip() if default else None,
                      'expiry': expiry.group(1).strip() if expiry else None,
                      'links': links, 'related_events': related,
                      'document_url': base + path.relative_to(ROOT).as_posix()})
    extras = read_json(ROOT / 'dashboard/catalog.json')
    for eid, entry in extras['events'].items():
        if eid not in ids:
            raise ValueError('Unknown catalog event: ' + eid)
        wt = entry.get('webtoon')
        if wt and wt['status'] not in ('todo', 'done', 'excluded'):
            raise ValueError('Invalid webtoon status')
        if wt and wt['status'] == 'done' and not wt.get('url'):
            raise ValueError('Completed webtoon needs a result link')
        for media in entry.get('media', []):
            if media['type'] not in ('image', 'video', 'link') or not media['url'].startswith('https://'):
                raise ValueError('Invalid media')
    output.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'style.css', 'app.js', 'webtoon-feed.js'):
        shutil.copy2(ROOT / 'dashboard' / name, output / name)
    payload = {'events': events, 'flags': flags, 'catalog': extras, 'source': {'ref': ref, 'sha': sha},
               'built_at': datetime.now(timezone.utc).isoformat(),
               'updated_at': max(d.get('assessed_at') or d.get('observed_at') or '' for d in events)}
    (output / 'data.json').write_text(json.dumps(payload, ensure_ascii=False))
    (output / '.nojekyll').touch()
    print(f'Built {len(events)} events, {len(set(d["feature_id"] for d in events))} features, {len(flags)} flags → {output}')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    build(parser.parse_args().output)
