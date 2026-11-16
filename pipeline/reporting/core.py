"""Deterministic KST daily changes, immutable report revisions and public evidence."""
import copy
import hashlib
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.normalize import load_dataset, publish, validate_graph
from pipeline.normalize.storage import PATHS, records
from pipeline.selection import as_of, catalog_transitions
from pipeline.selection.core import semantic
from schemas.validate import ContractError, validate_record

KST = ZoneInfo('Asia/Seoul')
VERSION = 'daily-selected-v1'
STATES = ('complete', 'partial', 'failed', 'unknown')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('A cutoff must include its timezone')
    return result.astimezone(timezone.utc)


def utc(value):
    return instant(value).isoformat().replace('+00:00', 'Z')


def window(day, cutoff, previous_cutoff=None):
    day = date.fromisoformat(day)
    end = instant(cutoff)
    start = datetime.combine(day, time(), KST).astimezone(timezone.utc)
    if end.astimezone(KST).date() != day:
        raise ValueError('Cutoff must fall on the report date in Asia/Seoul')
    previous = instant(previous_cutoff) if previous_cutoff else start - timedelta(microseconds=1)
    if previous >= end or previous >= start:
        raise ValueError('Previous cutoff must precede the report day and cutoff')
    return previous.isoformat().replace('+00:00', 'Z'), utc(cutoff)


def path_index(repository, dataset):
    result = {}
    for kind in ('source_item', 'feature_event', 'experiment_event', 'assessment'):
        field = 'source_item_id' if kind == 'source_item' else 'assessment_id' if kind == 'assessment' else 'event_id'
        for path in sorted(Path(repository).glob(PATHS[kind])):
            for record in records(json.loads(path.read_text())):
                result[kind, record[field]] = path.relative_to(repository).as_posix()
    return result


def timing(subject, assessment, day):
    if subject.get('event_type') == 'correction' or subject.get('correction_of') or subject.get('revision', 1) > 1:
        return 'correction'
    if assessment['supersedes']:
        return 'reclassification'
    if subject.get('origin') in ('baseline', 'backfill') or subject.get('event_type') == 'baseline':
        return 'backfill'
    announcement = subject.get('announced_at') or subject.get('published_at') or subject.get('effective_at')
    if announcement and announcement < day:
        return 'late_observation'
    return 'current'


def judged_subject(root, subject, assessment, path):
    """Resolve the assessed facts, including an archived corrected event."""
    revision = assessment.get('input_revision') or ''
    if revision.startswith(('semantic-sha256:', 'semantic-v2-sha256:')):
        legacy = revision.startswith('semantic-sha256:')
        expected = revision.split(':', 1)[1]
        if digest(semantic(subject, legacy=legacy)) == expected:
            return subject, path
        candidates = []
        if assessment['subject_kind'].endswith('_event'):
            for archive in sorted(root.glob('data/event-revisions/' + assessment['subject_id'] + '/*.json')):
                candidates.append((json.loads(archive.read_text()), archive.relative_to(root).as_posix()))
        else:
            for snapshot in subject.get('revisions', []):
                candidate = copy.deepcopy(subject)
                candidate.update({k: v for k, v in snapshot.items() if k in candidate})
                if 'item_content_sha256' not in snapshot:
                    candidate.pop('item_content_sha256', None)
                candidates.append((candidate, path))
        for candidate, candidate_path in candidates:
            if digest(semantic(candidate, legacy=legacy)) == expected:
                return candidate, candidate_path
        raise ContractError('Assessed facts are unavailable; retain the last report and restore the fact archive')
    if assessment.get('evaluator') == 'legacy' and ':sha256:' in revision:
        archive_path, expected = revision.rsplit(':sha256:', 1)
        archive = root / archive_path
        if archive_path.startswith('data/event-revisions/') and archive.is_file():
            original = json.loads(archive.read_text())
            if digest(original) != expected:
                raise ContractError('Legacy assessed fact archive hash mismatch')
            result = copy.deepcopy(subject)
            result.update(original)
            result['revision'] = original.get('revision', 1)
            return result, archive_path
    return subject, path


def make_item(change, kind, dataset, paths, day, cutoff, documentation, root):
    fields = {'source_item': 'source_item_id', 'feature_event': 'event_id', 'experiment_event': 'event_id'}
    subject = next(r for r in dataset[change['subject_kind']] if r[fields[change['subject_kind']]] == change['subject_id'])
    assessment = next(r for r in dataset['assessment'] if r['assessment_id'] == change['assessment_id'])
    subject, subject_path = judged_subject(root, subject, assessment, paths[change['subject_kind'], change['subject_id']])
    sources = {r['source_item_id']: r for r in dataset['source_item']}
    evidence = []
    # Freeze evidence available at the judgment time, not a later mutable source head.
    for ident in sorted(assessment['evidence_source_item_ids']):
        source = sources[ident]
        revisions = [r for r in source['revisions'] if not r.get('restores_revision_id') and instant(r['observed_at']) <= instant(cutoff)]
        if not revisions:
            raise ContractError('No source evidence exists at the requested cutoff: ' + ident)
        judgment_revisions = [r for r in revisions if instant(r['observed_at']) <= instant(assessment['assessed_at'])]
        order = lambda r: (instant(r['observed_at']), r['revision_id'])
        revision = max(judgment_revisions, key=order) if judgment_revisions else min(revisions, key=order)
        ev = revision['evidence']
        evidence.append(dict(source_item_id=ident, revision_id=revision['revision_id'], content_sha256=revision['content_sha256'],
                             source_revision=revision['source_revision'], url=ev['url'], observed_at=revision['observed_at'],
                             section=ev.get('section'), excerpt=ev.get('excerpt'), record_path=paths['source_item', ident]))
    if not evidence:
        raise ContractError('Report items require public evidence')
    if change['subject_kind'] == 'source_item':
        own = next((e for e in evidence if e['source_item_id'] == change['subject_id']), None)
        if own:
            snapshot = next(r for r in sources[change['subject_id']]['revisions'] if r['revision_id'] == own['revision_id'])
            subject = copy.deepcopy(subject)
            subject.update({k: v for k, v in snapshot.items() if k in subject})
    if instant(subject['observed_at']) > instant(cutoff):
        raise ContractError('Subject facts postdate cutoff; use a stored report revision')
    first_source = sources[evidence[0]['source_item_id']]
    after = subject.get('after') or {}
    details = dict(title=subject.get('title') or subject.get('summary') or change['subject_id'],
                   summary=subject.get('delta') or subject.get('summary') or '',
                   browser=subject.get('browser', first_source['browser']),
                   channel=subject.get('channel', first_source.get('channel')),
                   platform=subject.get('platform', after.get('platform', first_source.get('platform', []))),
                   workstreams=subject.get('workstreams', []), ai_related=subject.get('ai_related'),
                   event_type=subject.get('event_type'), subject_revision=subject.get('revision'),
                   status=assessment['status'], priority=assessment['priority'], assessment_rule_version=assessment['rule_version'],
                   reasons=assessment['reasons'], comparison_question=assessment['comparison_question'],
                   benchmark_readiness=assessment['benchmark_readiness'], benchmark=assessment.get('benchmark') or subject.get('benchmark_candidate'),
                   subject_path=subject_path,
                   assessment_path=paths['assessment', assessment['assessment_id']], selection_path=f'data/selected/{kind}/current.json')
    details['documentation_paths'] = documentation.get(change.get('catalog_id'), [])
    return dict(subject_kind=change['subject_kind'], subject_id=change['subject_id'], assessment_id=change['assessment_id'],
                event_ids=change['event_ids'], change_id=change['change_id'], timing=timing(subject, assessment, day),
                announced_at=subject.get('announced_at') or subject.get('published_at'), observed_at=subject['observed_at'],
                source_urls=sorted({e['url'] for e in evidence}), selection_kind=kind, action=change['action'],
                discovered_at=change['effective_at'], effective_at=subject.get('effective_at'), evidence=evidence, details=details)


def escape(value):
    return str(value if value is not None else '미확인').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('[', '\\[').replace(']', '\\]').replace('\n', ' ')


def relative(target, markdown_path):
    return os.path.relpath(target, str(Path(markdown_path).parent)).replace(os.sep, '/')


def render(report):
    """Render only stored snapshots. No live graph or external model is consulted."""
    link = lambda label, path: f'[{label}]({relative(path, report["markdown_path"])})'
    status = report['completeness']
    lines = [f'# {report["date"]} 브라우저 선정 변화', '',
             f'- 기준: Asia/Seoul · cutoff `{report["cutoff"]}` · revision {report["revision"]}',
             f'- 비교 구간: `{report["previous_cutoff"]}` 이후부터 cutoff까지',
             f'- 수집: {status["collection"]} · 평가: {status["evaluation"]}',
             '- 공개 문헌과 소스에 따른 조사입니다. 실기 벤치마크는 미실행입니다.', '']
    if 'complete' != status['collection'] or 'complete' != status['evaluation']:
        lines += ['**범위 제한:** 수집 또는 평가가 완전하다고 확인되지 않았습니다. 아래 내용은 확인한 자료의 변화이며, 전체 범위의 무변화를 뜻하지 않습니다.', '']
    if report['outcome'] == 'no_changes':
        lines += ['확인한 수집·평가 범위에서 새 선정 변화가 없습니다.', '']
    elif not report['items'] and not report['catalog_transitions']:
        lines += ['새 선정 변화 여부를 확정할 수 없습니다. 수집·평가 상태를 확인해야 합니다.', '']
    lines += ['과거 보강·신규 선정은 신규 출시와 다릅니다. 발표일·적용일·원천 관측일·선정 확인일을 구분합니다.', '',
              '전체 현재 목록: ' + link('기능', 'data/selected/features/current.json') + ' · ' + link('실험', 'data/selected/flags/current.json') + '.', '']
    labels = {'backfill': '과거·기준 목록 보강', 'late_observation': '늦은 확인', 'correction': '근거 정정', 'reclassification': 'PM 재분류', 'current': '당일 확인'}
    actions = {'selected': '신규 선정', 'changed': '선정 내용 변경', 'deselected': '선정 해제', 'reselected': '재선정'}
    for item in report['items']:
        d = item['details']
        lines += [f'## {escape(d["browser"])} · {escape(d["title"])}', '',
                  f'- 분류: {actions[item["action"]]} / {labels[item["timing"]]} / {item["selection_kind"]}',
                  f'- 채널: {escape(d["channel"])} · 플랫폼: {escape(", ".join(d["platform"]))}',
                  f'- 발표일: {escape(item["announced_at"])} · 적용일: {escape(item["effective_at"])}',
                  f'- 원천 관측일: `{item["observed_at"]}` · 선정 확인일: `{item["discovered_at"]}`',
                  f'- 사실 유형: {escape(d["event_type"])} · 사실 revision: {escape(d["subject_revision"])}',
                  f'- 판정: {d["status"]} · 우선순위: {escape(d["priority"])} · 준비 상태: {d["benchmark_readiness"]}', '',
                  escape(d['summary']), '', '### PM 선별과 비교 과제', '']
        lines += ['- ' + escape(reason) for reason in d['reasons']]
        lines += ['', '비교 질문: ' + escape(d['comparison_question']), '']
        if d['benchmark']:
            lines += ['벤치마크 후보:', '']
            for key, value in d['benchmark'].items():
                if key != 'executed':
                    lines += [f'- {escape(key)}: {escape(" → ".join(map(str, value)) if isinstance(value, list) else value)}']
            lines += ['']
        if item['selection_kind'] == 'flags':
            lines += ['공개 소스 실험입니다. 등록·기본값은 제품 출시, 설치본 노출, 한국 제공 또는 실기 결과를 보증하지 않습니다.', '']
        lines += ['### 고정 근거와 이력', '',
                  '- ' + link('원천/사건 ' + item['subject_id'], d['subject_path']),
                  '- ' + link('판정 ' + item['assessment_id'], d['assessment_path']) + ' · 규칙 `' + d['assessment_rule_version'] + '`',
                  '- ' + link('선정 변화 ' + item['change_id'], d['selection_path'])]
        for ident in item.get('related_change_ids', []):
            lines += ['- 같은 구간의 이전 판단: ' + link(ident, d['selection_path'])]
        lines += ['- ' + link('기능/실험 설명', p) for p in d.get('documentation_paths', [])]
        for ev in item['evidence']:
            lines += [f'- [공식 출처]({ev["url"]}) · {escape(ev["section"])}',
                      '  - ' + link(ev['source_item_id'], ev['record_path']) + f' · revision `{ev["revision_id"]}` · SHA-256 `{ev["content_sha256"]}`']
            if ev['source_revision']:
                lines += [f'  - 소스 commit: `{ev["source_revision"]}`']
        lines += ['']
    if report['catalog_transitions']:
        lines += ['## 현재 카드의 사건 교체', '', '아래는 카탈로그의 대표 사건 변경입니다. 이전 사건에 새 해제 판정을 내렸다는 의미가 아닙니다.', '']
        for tr in report['catalog_transitions']:
            a, b = tr['previous'], tr['current']
            lines += [f'- `{tr["catalog_id"]}`: `{a["subject_id"]}` ({a["status"]}) → `{b["subject_id"]}` ({b["status"]}).',
                      f'  - 교체 ID: `{tr["transition_id"]}`.']
            for label, side in [('이전', a), ('현재', b)]:
                lines += ['  - ' + link(label + ' 사건/원천', side['subject_path']) + ' · ' + link(label + ' 판정', side['assessment_path'])]
        lines += ['']
    lines += ['고정 선정 스냅샷:', '']
    lines += ['- ' + link(Path(p).name, p) for p in report['selection_snapshot_paths']]
    lines += ['', '리포트 데이터: ' + link(report['report_id'] + ' revision ' + str(report['revision']), f'data/reports/history/{report["date"]}/revision-{report["revision"]}.json'), '']
    return '\n'.join(lines)


def run(repository, private_dir, *, day, cutoff, previous_cutoff=None, collection='unknown', evaluation='unknown', dry_run=False):
    """Generate one logical daily report; changed inputs append a revision.

    Completeness is caller evidence, never inferred from a nonempty graph. No run
    identifiers, private errors, credentials or coverage logs enter this record.
    """
    root = Path(repository).resolve()
    previous_cutoff, cutoff = window(day, cutoff, previous_cutoff)
    if collection not in STATES or evaluation not in STATES:
        raise ValueError('Invalid completeness state')
    dataset = validate_graph(root)
    paths = path_index(root, dataset)
    documentation = {}
    compatibility = root / 'data/compatibility/legacy-index.json'
    if compatibility.exists():
        for entry in json.loads(compatibility.read_text()).get('features', []):
            if (root / entry['path']).exists():
                for ident in entry['feature_ids']:
                    documentation.setdefault(ident, []).append(entry['path'])
    for experiment in dataset['experiment']:
        path = 'experiments/chrome/' + (experiment.get('flag_id') or '') + '.md'
        if experiment.get('flag_id') and (root / path).exists():
            documentation[experiment['experiment_id']] = [path]
    selected = as_of(root, cutoff)
    items = []
    for kind in ('features', 'flags'):
        for change in selected[kind]['history']:
            if instant(previous_cutoff) < instant(change['effective_at']) <= instant(cutoff):
                items.append(make_item(change, kind, dataset, paths, day, cutoff, documentation, root))
    # One change per assessment/subject. Rule changes remain separate linked
    # judgments; a source/event that did not change is never relisted tomorrow.
    items.sort(key=lambda i: (instant(i['discovered_at']), i['selection_kind'], i['change_id']))
    grouped = {}
    for item in items:
        key = item['subject_kind'], item['subject_id']
        earlier = grouped.get(key)
        item['related_change_ids'] = earlier.get('related_change_ids', []) + [earlier['change_id']] if earlier else []
        grouped[key] = item
    items = list(grouped.values())
    transitions = catalog_transitions(root, previous_cutoff, cutoff)
    for transition in transitions:
        for side in (transition['previous'], transition['current']):
            side['subject_path'] = paths[side['subject_kind'], side['subject_id']]
            side['assessment_path'] = paths['assessment', side['assessment_id']]
    snapshot_files = {f'data/selected/history/{day}/{kind}-{digest(selected[kind])}.json': selected[kind] for kind in ('features', 'flags')}
    completeness = dict(collection=collection, evaluation=evaluation)
    outcome = 'changes' if items or transitions else 'no_changes' if collection == evaluation == 'complete' else 'incomplete'
    payload = dict(schema_version=2, report_id='daily-' + day, date=day, timezone='Asia/Seoul', cutoff=cutoff,
                   previous_cutoff=previous_cutoff, generator_version=VERSION, rule_version=VERSION,
                   items=items, catalog_transitions=transitions, completeness=completeness, outcome=outcome,
                   selection_snapshot_paths=sorted(snapshot_files))
    # Include immutable snapshots and normalized cutoff; run IDs and clock time
    # have no role in report identity or input equality.
    input_hash = digest(payload)
    current_path = f'data/reports/current/{payload["report_id"]}.json'
    old = json.loads((root / current_path).read_text()) if (root / current_path).exists() else None
    if old and old['input_hash'] == input_hash:
        archive = root / f'data/reports/history/{day}/revision-{old["revision"]}.json'
        markdown = root / old['markdown_path']
        if not archive.exists() or json.loads(archive.read_text()) != old or not markdown.exists() or markdown.read_text() != render(old):
            raise ContractError('Stored report revision is missing or altered')
        return {'report': old, 'created': False, 'replacements': {}, 'text_files': {}}
    if old and instant(cutoff) < instant(old['cutoff']):
        raise ContractError('Cannot move the current daily cutoff backwards; read the stored revision')
    revision = old['revision'] + 1 if old else 1
    report = dict(payload, revision=revision, supersedes_revision=old['revision'] if old else None,
                  input_hash=input_hash, markdown_path=f'reports/generated/{day}/r{revision}.md')
    validate_record('report', report)
    replacements = dict(snapshot_files)
    replacements[current_path] = report
    replacements[f'data/reports/history/{day}/revision-{revision}.json'] = report
    validate_graph(root, replacements)
    text_files = {report['markdown_path']: render(report)}
    reports = {r['report_id']: r for r in dataset['report']}
    reports[report['report_id']] = report
    index = ['# 자동 생성 선정 변화 리포트', '', '날짜별 최신 revision입니다. 각 리포트의 고정 데이터와 이전 revision은 보존합니다.', '']
    for r in sorted(reports.values(), key=lambda r: r['date'], reverse=True):
        index += [f'- [{r["date"]} · revision {r["revision"]}]({relative(r["markdown_path"], "reports/generated/README.md")}) · {r.get("outcome", "unknown")}']
    text_files['reports/generated/README.md'] = '\n'.join(index) + '\n'
    if not dry_run:
        publish(root, replacements, private_dir, text_files=text_files)
    return {'report': report, 'created': True, 'replacements': replacements, 'text_files': text_files}
