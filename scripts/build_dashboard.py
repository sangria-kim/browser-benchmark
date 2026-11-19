"""Build a static public dashboard from the repository's evidence."""
import argparse
import gzip
import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def write_resource(output, path, value):
    """Only generated lazy resources use deterministic gzip; data.json stays plain."""
    target = output / path
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if path.endswith('.json.gz'):
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as stream:
            stream.write(content)
        content = buffer.getvalue()
    target.write_bytes(content)


def read_resource(path):
    """Read a generated dashboard resource, including the plain entry file."""
    content = path.read_bytes()
    return json.loads(gzip.decompress(content) if path.name.endswith('.json.gz') else content)


def read_json(path):
    return json.loads(path.read_text())


def build_research(output, legacy, base):
    """Emit small entry data and lazy immutable-ID detail/report resources.

    No collector or evaluator runs here. Dated membership uses assessment time,
    with the same latest-successful owner ordering as selection.core.project.
    """
    import hashlib
    sys.path.insert(0, str(ROOT))
    from pipeline.selection.core import build_contexts, latest_assessments, project, load_rules
    from pipeline.temporal import policy
    from pipeline.normalize.storage import load_source_items
    from collections import defaultdict, Counter
    from datetime import timedelta

    def records(pattern):
        result = []
        for path in sorted(ROOT.glob(pattern)):
            value = read_json(path)
            result.extend(value if isinstance(value, list) else [value])
        return result

    def stamp(value):
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)

    def day(value):
        return (stamp(value) + timedelta(hours=9)).date().isoformat()

    def key(kind, identifier):
        return kind + ':' + identifier

    def resource(identifier):
        return 'details/' + hashlib.sha256(identifier.encode()).hexdigest() + '.json.gz'

    def write(path, value):
        write_resource(output, path, value)

    groups = {
        'source_item': load_source_items(ROOT),
        'feature': records('data/catalog/features/*.json'),
        'feature_event': legacy['events'],
        'experiment': records('data/catalog/chrome-experiments/*.json'),
        'experiment_event': records('data/experiment-events/*.json'),
    }
    fields = {'source_item':'source_item_id', 'feature':'feature_id', 'feature_event':'event_id',
              'experiment':'experiment_id', 'experiment_event':'event_id'}
    objects = {key(kind, r[fields[kind]]): r for kind, rows in groups.items() for r in rows}
    assessments = records('data/assessments/*/*.json')
    dataset = dict(groups, assessment=assessments, selected=records('data/selected/*/current.json'))
    contexts, coverage = build_contexts(dataset)
    histories = defaultdict(list)
    for a in assessments:
        histories[key(a['subject_kind'], a['subject_id'])].append(a)
    for history in histories.values():
        history.sort(key=lambda a: (stamp(a['assessed_at']), a['assessment_id']))
    catalogs, source_owners, owner_subjects = {}, defaultdict(list), defaultdict(list)
    for kind in ('feature', 'experiment'):
        for c in groups[kind]:
            cid = c[fields[kind]]
            catalogs[cid] = (kind, c)
            for sid in c['source_item_ids']:
                source_owners[sid].append(cid)
    # Feature summaries and detail cards must use the same confirmed source snapshots.
    catalog_evidence = {}
    for cid, (_, catalog) in catalogs.items():
        refs = []
        for sid in catalog['source_item_ids']:
            source = objects[key('source_item', sid)]
            pins = catalog.get('source_revision_ids', {}).get(sid)
            if pins:
                source = next(r for r in reversed(source['revisions']) if r['revision_id'] == pins[-1])
            refs.append((sid, source))
        catalog_evidence[cid] = refs

    def owner(k):
        fact = objects[k]
        if k.startswith('feature_event:'):
            return fact['feature_id']
        if k.startswith('experiment_event:'):
            return fact['experiment_id']
        if k.startswith('source_item:'):
            owners = source_owners[fact['source_item_id']]
            return owners[0] if len(owners) == 1 else None
        return fact.get('feature_id') or fact.get('experiment_id')
    for k in objects:
        if not k.startswith(('feature_event:', 'experiment_event:')) and k not in histories:
            continue
        cid = owner(k)
        if cid:
            owner_subjects[cid].append(k)
    def heads_at(cutoff=None):
        return {key(*k): a for k,a in latest_assessments(assessments, cutoff).items()}
    def active_at(heads):
        active = {}
        for k, a in heads.items():
            if tuple(k.split(':', 1)) not in contexts:
                continue
            fact = objects[k]
            rank = (stamp(fact['observed_at']), a['subject_id']) if a['subject_kind'].endswith('_event') else (stamp(a['assessed_at']), a['subject_id'])
            cid = owner(k) or k
            if cid not in active or rank > active[cid][0]:
                active[cid] = (rank, k, a)
        return {cid: (k, a) for cid, (_, k, a) in active.items()}
    heads = heads_at()
    active = active_at(heads)
    current_keys = {k for k, a in active.values() if a['status'] == 'selected'}
    # Principal evidence mapping includes T5's exact cross-document matches.
    principals = {sid:key(*k) for sid,k in coverage.items()}
    def principal(k):
        if k in histories:
            return k
        if k.startswith('source_item:'):
            return principals.get(objects[k]['source_item_id'], k)
        cid = owner(k)
        return active.get(cid, (k, None))[0]
    def brief(k, chosen=None):
        fact = objects[k]
        pk = principal(k)
        a = chosen or heads.get(pk)
        cid = owner(k)
        catalog = catalogs.get(cid, (None, {}))[1]
        after = fact.get('after') or {}
        if not isinstance(after, dict):
            after = {}
        title = fact.get('feature_title') or after.get('title') or fact.get('title') or fact.get('summary') or fact.get('symbol') or k.split(':', 1)[1]
        platforms = fact.get('platform') or after.get('platform') or catalog.get('platform') or []
        refs = catalog_evidence.get(cid, [])
        versions = sorted({source['version'] for _, source in refs if source.get('version')})
        if not versions and fact.get('version'):
            versions = [fact['version']]
        dates = [fact.get('observed_at')]
        if k.startswith(('feature:', 'experiment:')):
            dates += [source['observed_at'] for _, source in refs]
        return {'key': k, 'id': k.split(':',1)[1], 'subject_kind': k.split(':',1)[0],
                'title': title, 'browser': fact.get('browser') or catalog.get('browser') or 'chrome',
                'platform': platforms if isinstance(platforms,list) else [platforms],
                'versions': versions,
                'date': max(filter(None, dates), key=stamp, default=''), 'catalog_id': cid,
                'experiment_kind': fact.get('experiment_kind') or catalog.get('experiment_kind'),
                'event_type': fact.get('event_type'), 'build_conditions': after.get('build_conditions', fact.get('build_conditions', [])),
                'ai_related': fact.get('ai_related', False),
                'status': a['status'] if a else 'unassessed', 'assessment_id': a['assessment_id'] if a else None,
                'current_status': heads.get(pk, {}).get('status', 'unassessed'),
                'current_selected': pk in current_keys, 'principal': pk,
                'temporal_scope': ((catalog.get('temporal_scope') or fact.get('temporal_scope')) if fact.get('experiment_kind')
                                   else (fact.get('temporal_scope') or catalog.get('temporal_scope'))),
                'detail': resource(k)}
    projections = {p['selection_kind']: p for p in records('data/selected/*/current.json')}
    actual_keys = {key(r['subject_kind'],r['subject_id']) for p in projections.values() for r in p['current']}
    if actual_keys != current_keys:
        raise ValueError('Dashboard projection differs from current selected contract')
    changes = defaultdict(list)
    for p in projections.values():
        for change in p['history']:
            changes[key(change['subject_kind'],change['subject_id'])].append(change)
    # Use current histories once. Dated archives repeat history, so never union them.
    ever = set(changes)
    date_index = []
    for d in sorted({day(a['assessed_at']) for a in assessments}, reverse=True):
        cutoff = d + 'T23:59:59.999999+09:00'
        dated = project(dataset, contexts, assessments, load_rules(), cutoff, as_of=cutoff)
        date_heads = heads_at(cutoff)
        rows = [brief(key(r['subject_kind'],r['subject_id']), date_heads[key(r['subject_kind'],r['subject_id'])]) for p in dated.values() for r in p['current']]
        path = 'dates/' + d + '.json.gz'
        write(path, {'date':d, 'cutoff':cutoff, 'rows':rows})
        date_index.append({'date':d, 'path':path, 'count':len(rows)})
    report_index, report_links = [], defaultdict(list)
    reports = records('data/reports/history/*/*.json')
    for report in reports:
        path = 'reports/' + report['date'] + '-r' + str(report['revision']) + '.json.gz'
        write(path, report)
        entry = {k:report[k] for k in ('report_id','date','revision','cutoff','completeness','outcome')}
        entry.update(path=path, count=len(report['items']), markdown=base+'reports/generated/'+report['date']+'/r'+str(report['revision'])+'.md')
        report_index.append(entry)
        for item in report['items']:
            report_links[key(item['subject_kind'],item['subject_id'])].append(entry)
    legacy_flags = {f['id']: f for f in legacy['flags']}
    docs = defaultdict(list)
    compat_path = ROOT/'data/compatibility/legacy-index.json'
    if compat_path.exists():
        for mapping in read_json(compat_path)['flags']:
            for cid in mapping['experiment_ids']:
                if mapping['flag_id'] in legacy_flags:
                    docs[cid].append(legacy_flags[mapping['flag_id']])
    for k, fact in objects.items():
        cid = owner(k)
        pk = principal(k)
        related = owner_subjects.get(cid, [])
        if k.startswith(('feature:', 'experiment:')):
            refs = catalog_evidence[cid]
        else:
            source_ids = [fact['source_item_id']] if k.startswith('source_item:') else fact['source_item_ids']
            refs = [(sid, objects[key('source_item', sid)]) for sid in source_ids]
        evidence = []
        for sid, source in refs:
            citation = dict(source['evidence'], key=key('source_item', sid), detail=resource(key('source_item', sid)))
            if 'revision_id' in source:
                citation['revision_id'] = source['revision_id']
            evidence.append(citation)
        revisions = []
        if k.startswith(('feature_event:', 'experiment_event:')):
            for p in sorted((ROOT/'data/event-revisions'/fact['event_id']).glob('*.json')):
                revisions.append(read_json(p))
        relation_rows = []
        for relation in fact.get('relationships', []) + (fact.get('after', {}).get('relationships', []) if isinstance(fact.get('after'), dict) else []):
            target = relation.get('target_id') or relation.get('experiment_id') or relation.get('feature_id')
            if target in catalogs:
                relation_rows.append(brief(key(catalogs[target][0], target)))
        write(resource(k), {'relationships':relation_rows, 'row':brief(k), 'fact':fact, 'assessments':histories.get(pk, []),
                            'assessment_subject':pk, 'selection_history':changes.get(pk, []),
                            'current_owner':brief(active[cid][0]) if cid in active else None,
                            'related':[brief(r) for r in related if r != k], 'evidence':evidence,
                            'revisions':revisions, 'reports':report_links.get(k, []),
                            'legacy_flags':docs.get(cid, [])})
    all_rows = {kind:[brief(key(kind,r[fields[kind]])) for r in groups[kind]] for kind in ('source_item','feature','experiment')}
    for kind, rows in all_rows.items():
        write('indexes/'+kind+'.json.gz', rows)
    selected_rows = {kind:[brief(key(r['subject_kind'],r['subject_id'])) for r in projections.get(kind,{}).get('current',[])] for kind in ('features','flags')}
    initial = {'format_version':2, 'resource_encoding':'gzip', 'source':legacy['source'], 'built_at':legacy['built_at'],
               'updated_at':max((a['assessed_at'] for a in assessments),default=legacy['updated_at']),
               'catalog':legacy['catalog'], 'selected':selected_rows,
               'card_summaries':read_json(ROOT / 'dashboard/card-summaries.json'),
               'history':[brief(k) for k in sorted(ever)], 'dates':date_index,
               'reports':sorted(report_index,key=lambda r:(r['date'],r['revision']),reverse=True),
               'counts':{kind:len(rows) for kind,rows in groups.items()},
               'experiment_counts':dict(Counter(r['experiment_kind'] for r in groups['experiment'])),
               'assessment_count':len(assessments),
               'indexes':{k:'indexes/'+k+'.json.gz' for k in all_rows}}
    if policy(dataset):
        initial['collection_scope'] = policy(dataset)
    write('data.json',initial)
    rendered = read_resource(output / 'data.json')
    for kind, projection in projections.items():
        expected = {(r['subject_kind'], r['subject_id'], r['assessment_id']) for r in projection['current']}
        actual = {(r['subject_kind'], r['id'], r['assessment_id']) for r in rendered['selected'][kind]}
        if expected != actual:
            raise ValueError('Dashboard differs from selected ' + kind)
    for entry in rendered['reports']:
        source = ROOT / 'data/reports/history' / entry['date'] / f"revision-{entry['revision']}.json"
        if read_resource(output / entry['path']) != read_json(source):
            raise ValueError('Dashboard differs from report ' + entry['report_id'])
    from scripts.build_daily_dashboard import write_home
    write_home(output, ROOT, legacy, reports, projections.get('features', {}))
    return initial


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
    for name in ('details', 'indexes', 'dates', 'reports'):
        if (output / name).exists():
            shutil.rmtree(output / name)
    shutil.copy2(ROOT / 'dashboard/index.html', output / 'research.html')
    for name in ('style.css', 'app.js', 'webtoon-feed.js', 'research-model.js', 'resources.js'):
        shutil.copy2(ROOT / 'dashboard' / name, output / name)
    payload = {'events': events, 'flags': flags, 'catalog': extras, 'source': {'ref': ref, 'sha': sha},
               'built_at': datetime.now(timezone.utc).isoformat(),
               'updated_at': max(d.get('assessed_at') or d.get('observed_at') or '' for d in events)}
    payload['research'] = build_research(output, payload, base)
    (output / '.nojekyll').touch()
    print(f'Built {len(events)} events, {len(set(d["feature_id"] for d in events))} features, {len(flags)} flags → {output}')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    build(parser.parse_args().output)
