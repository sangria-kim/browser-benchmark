"""Evidence-gated public PM evaluation; no network, credentials or hidden scoring."""
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pipeline.normalize import load_dataset, publish, validate_graph
from pipeline.normalize.storage import PATHS, records
from schemas.validate import ContractError, validate_record, validate_transition
from pipeline.temporal import eligible, context_scope, policy, scope_semantics

ROOT = Path(__file__).resolve().parents[2]
PM_FIELDS = {'selection_status', 'selection_reason', 'priority', 'priority_reason',
             'comparison_question', 'benchmark_readiness', 'revisit_trigger',
             'assessed_at', 'selection_rule_version'}
NOISE = PM_FIELDS | {'observed_at', 'source_revision', 'previous_source_revision',
                    'revision_id', 'line_start', 'line_end',
                    'revisions', 'revision', 'source_locations', 'temporal_scope'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def semantic(value, *, legacy=False):
    """Keep evidence text and actual facts; drop capture/provenance-only changes."""
    if isinstance(value, dict):
        result = {k: semantic(v, legacy=legacy) for k, v in value.items()
                  if k not in NOISE and not (legacy and k == 'item_content_sha256')}
        if not legacy and value.get('source_item_id') and value.get('item_content_sha256'):
            # Only browser items with a complete item digest can separate their
            # raw document integrity hash from semantic evaluation input.
            result['evidence'].pop('content_sha256', None)
        return result
    if isinstance(value, list):
        return [semantic(v, legacy=legacy) for v in value]
    if isinstance(value, str):
        # Pinned Chromium URLs are provenance. Their file path remains semantic.
        return re.sub(r'(?<=/)[0-9a-f]{40}(?=/|$)', '<revision>', value)
    return value


def key(record):
    return record['subject_kind'], record['subject_id']


def load_rules(path=None):
    result = json.loads(Path(path or ROOT / 'rules/pm/pm-selection-v3.json').read_text())
    if not result.get('rule_version') or not result.get('prompt_version'):
        raise ValueError('Rules need rule_version and prompt_version')
    return result


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def event_time(event):
    # Observation is ordering metadata only. It is not a release date.
    return timestamp(event['observed_at']), event['event_id']


def build_contexts(dataset):
    """Every source is mapped to a principal subject or evaluated independently.

    Historical events remain subjects. Catalog-only legacy source evidence maps
    to its latest event. Exact document text can connect separately collected
    evidence; title similarity is never used.
    """
    sources = {s['source_item_id']: s for s in dataset['source_item']}
    contexts, coverage, catalog_sources = {}, {}, {}
    for kind in ('feature', 'experiment'):
        for catalog in dataset[kind]:
            for sid in catalog['source_item_ids']:
                catalog_sources.setdefault(sid, []).append((kind, catalog))
    for kind in ('feature_event', 'experiment_event'):
        owner_kind = kind.replace('_event', '')
        owners = {r[owner_kind + '_id']: r for r in dataset[owner_kind]}
        for event in sorted(dataset[kind], key=event_time):
            k = kind, event['event_id']
            catalog = owners[event[owner_kind + '_id']]
            contexts[k] = {'subject_kind': kind, 'subject_id': event['event_id'],
                           'subject': event, 'catalog': catalog,
                           'sources': [sources[s] for s in event['source_item_ids']]}
            for sid in event['source_item_ids']:
                coverage[sid] = k
    for sid, candidates in catalog_sources.items():
        if sid in coverage or len(candidates) != 1:
            continue
        kind, catalog = candidates[0]
        events = [contexts[(kind + '_event', eid)]['subject'] for eid in catalog['event_ids']]
        if events:
            coverage[sid] = kind + '_event', max(events, key=event_time)['event_id']
    # Strict text+document+product+channel+version identity only.
    def document(url):
        u = urlsplit(url)
        return urlunsplit((u.scheme, u.netloc, u.path.rstrip('/'), u.query, ''))
    def evidence_keys(s):
        prefix = (s['browser'], s['channel'], s['version'], tuple(sorted(s['platform'])),
                  document(s['evidence']['url']))
        excerpt = s['evidence'].get('excerpt')
        # Section headings identify a container, never an individual item.
        # Browser collectors cap public excerpts at 220 characters. Matching
        # truncated prefixes cannot prove that two units are the same.
        return [prefix + (' '.join(excerpt.split()),)] if excerpt and 40 < len(excerpt) < 220 else []
    known = {}
    anchors = {}
    for sid, principal in coverage.items():
        for evidence_key in evidence_keys(sources[sid]):
            known.setdefault(evidence_key, set()).add(principal)
        source = sources[sid]
        url = source['evidence']['url']
        if urlsplit(url).fragment:
            anchors.setdefault((source['browser'], source['channel'], url), set()).add(principal)
    for sid, source in sources.items():
        if sid not in coverage:
            matches = set().union(*(known.get(k, set()) for k in evidence_keys(source)))
            location = source.get('source_location') or ''
            # An exact upstream item anchor can supply identity when the parser
            # lacks a separate version field (for example a versioned Firefox URL).
            if urlsplit(location).fragment == source['item_key']:
                for principal in anchors.get((source['browser'], source['channel'], location), set()):
                    old_platform = set(contexts[principal]['subject'].get('platform', ['unknown']))
                    new_platform = set(source['platform'])
                    if old_platform == new_platform or 'unknown' in old_platform or 'unknown' in new_platform:
                        matches.add(principal)
            if len(matches) == 1:
                coverage[sid] = next(iter(matches))
        if sid not in coverage:
            k = 'source_item', sid
            candidates = catalog_sources.get(sid, [])
            catalog = candidates[0][1] if len(candidates) == 1 else None
            contexts[k] = {'subject_kind': k[0], 'subject_id': sid, 'subject': source,
                           'catalog': catalog, 'sources': [source]}
            coverage[sid] = k
    # Coverage is also an evidence contract. Every path above (including a
    # catalog-only source) must supply its mapped evidence to the evaluator and
    # cache. Preserve historical event evidence even when its coverage principal
    # is a later event. Sort by stable source identity, never input file order.
    evidence = {k: {s['source_item_id'] for s in c['sources']} for k, c in contexts.items()}
    for sid, principal in coverage.items():
        evidence[principal].add(sid)
    for k, source_ids in evidence.items():
        contexts[k]['sources'] = [sources[sid] for sid in sorted(source_ids)]
    return contexts, coverage


def input_hash(context, rules, model_id=None, revisit=None):
    # Catalog current facts must not retroactively change historical event inputs.
    subject = context['subject']
    catalog_identity = {k: context['catalog'].get(k) for k in
                        ('feature_id', 'experiment_id', 'experiment_kind', 'canonical_key')} if context['catalog'] else None
    return digest({'subject': semantic(subject),
                   'sources': [semantic(s) for s in context['sources']],
                   **({'temporal_scope': scope_semantics(context_scope(context))} if context_scope(context) else {}),
                   'catalog_identity': catalog_identity, 'rules': rules,
                   'model_id': model_id, 'revisit': revisit})


def decision(status, reason, *, priority=None, question=None, readiness='unknown', revisit=None):
    return {'status': status, 'reasons': [reason], 'priority': priority,
            'comparison_question': question, 'benchmark_readiness': readiness,
            'revisit_trigger': revisit}


def evaluate(context, rules):
    if not eligible(context):
        scope = context_scope(context)
        return decision('excluded', 'Outside the confirmed collection projection (%s): %s This is not evidence of product removal.' % (scope['status'], scope['reason']))
    subject = context['subject']
    facts = subject.get('after') or subject
    profiles = rules['profiles']
    for profile in profiles:
        match = profile['match']
        identity = facts.get(match['field'])
        if identity != match['value']:
            continue
        evidence = facts.get(profile['evidence_field']) or ''
        if evidence != profile['evidence_equals']:
            continue
        if any(s['record_status'] == 'unparsed' for s in context['sources']):
            break
        if context['subject_kind'] == 'experiment_event' and facts.get('lifecycle') != 'active':
            return decision('watch', 'The documented experiment is not active in this source snapshot. ' + profile['impact'], readiness='conditional', revisit='Confirm an active source registration and an accessible build.')
        result = decision(profile['status'], 'Evidence-gated deterministic profile %s: %s' % (profile['id'], profile['impact']),
                          priority=profile.get('priority'), question=profile['question'],
                          readiness='conditional', revisit=profile['conditions'])
        result['reasons'].extend(['Evidence: ' + evidence,
                                  'Material change: ' + profile['material_change'],
                                  'Benchmark: ' + ' → '.join(profile['steps']),
                                  'Measure: ' + '; '.join(profile['metrics']),
                                  'Completion: ' + profile['completion'],
                                  'Conditions: ' + profile['conditions']])
        return result
    task_result = evaluate_task_profile(context, rules)
    if task_result:
        return task_result
    text = subject.get('summary') or subject.get('title') or ''
    if text in rules['generic_updates']:
        return decision('excluded', 'The complete stored statement is generic maintenance: %s No concrete changed user task or comparison procedure is specified.' % text,
                        revisit='An official item specifies a changed user task or reproducible failure.')
    if subject.get('item_type') == 'security':
        return decision('excluded', 'The source classifies this item as a security update. The public evidence has no reviewed benchmark task: ' + text,
                        revisit='Document a changed user workflow or security control with a specific comparison task.')
    return decision('pending_verification', 'Evidence retained for %s: %s A verified material change and a concrete comparison procedure are not yet jointly established by a public benchmark profile.' % (context['subject_id'], text),
                    revisit='Add or review exact public evidence, user impact, comparison steps, metrics and access conditions. Source presence alone does not prove release or testing.')


def evaluate_task_profile(context, rules):
    """Reusable, transparent text gates; these are not semantic model judgments.

    A score or topic keyword never selects an item. Require an affirmative clause
    that states a concrete user action plus an appropriate research task template.
    Conditions and testing remain unknown until separately verified.
    """
    subject = context['subject']
    experiment = subject.get('experiment_kind') is not None
    facts = subject.get('after') or subject
    text = facts.get('description') if experiment else subject.get('summary')
    if not text or not all(s['record_status'] == 'parsed' and s['source_id'] != 'legacy' for s in context['sources']):
        return None
    # Require the action clause in actual source text, not only an interpretation.
    evidence_text = '\n'.join((s['evidence'].get('excerpt') or '') + '\n' + (s['evidence'].get('section') or '') for s in context['sources'])
    if experiment:
        if context['subject_kind'] != 'experiment_event' or not facts.get('source_definition'):
            return None
        evidence_text += '\n' + (facts.get('description') or '')
    for profile in rules.get('task_profiles', []):
        pattern = profile['experiment_pattern' if experiment else 'announcement_pattern']
        match = re.search(pattern, text, re.IGNORECASE)
        if not match or match.group(0).casefold() not in evidence_text.casefold():
            continue
        uncertain = re.search(rules['uncertain_pattern'], text, re.IGNORECASE)
        conditions = ('Source-only registration. Confirm a compatible build, platform, actual exposure and relevant option before testing.' if experiment else
                      'Official document observation. Confirm the stated channel, OS, account and regional availability before testing.')
        conditions += ' Use identical synthetic data and an available Samsung Browser build. Record unsupported paths; no installation, rollout or completed test is inferred.'
        status = 'watch' if uncertain or (experiment and facts.get('lifecycle') != 'active') else 'selected'
        result = decision(status, 'Deterministic task-template match %s: %s' % (profile['id'], profile['impact']),
                          priority=profile['priority'] if status == 'selected' else None,
                          question=profile['question'], readiness='conditional', revisit=conditions)
        result['reasons'].extend([
            'Evidence clause: ' + match.group(0),
            'Material change: ' + ('An existing source registration documents this conditional action. Baseline research selection does not date introduction.' if experiment else
                                   'The official item explicitly describes a changed user action. This is selection of documented evidence, not a claim that the feature launched on assessment day.'),
            'Benchmark: ' + ' → '.join(profile['steps']),
            'Measure: ' + '; '.join(profile['metrics']),
            'Completion: Repeat each supported condition three times and record outcomes. The benchmark is not executed.',
            'Conditions: ' + conditions])
        if uncertain:
            result['reasons'].append('Selection withheld: uncertainty or negation marker in evidence: ' + uncertain.group(0))
        return result
    return None


def provider_decision(raw, context):
    """Reject invalid, ungrounded or unstructured model output before publication."""
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ContractError('Provider must return a JSON object')
    required = set(decision('watch', 'placeholder')) | {'evidence_source_item_ids'}
    if not required.issubset(raw) or set(raw) - required - {'benchmark'}:
        raise ContractError('Provider decision fields differ from the response contract')
    evidence = raw['evidence_source_item_ids']
    if not isinstance(evidence, list) or len(set(evidence)) != len(evidence) or set(evidence) != {s['source_item_id'] for s in context['sources']}:
        raise ContractError('Provider evidence differs from subject evidence')
    result = {k: copy.deepcopy(v) for k, v in raw.items() if k in required - {'evidence_source_item_ids'}}
    if raw['status'] == 'selected':
        benchmark = raw.get('benchmark')
        fields = {'user_impact', 'material_change', 'steps', 'metrics', 'conditions', 'completion', 'evidence_quotes'}
        if not isinstance(benchmark, dict) or set(benchmark) != fields:
            raise ContractError('Selected provider response needs all five evidence criteria')
        for field in fields:
            value = benchmark[field]
            if field in ('steps', 'metrics', 'evidence_quotes'):
                if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
                    raise ContractError('Benchmark lists must contain nonempty strings')
            elif not isinstance(value, str) or not value.strip():
                raise ContractError('Benchmark text must be nonempty')
        evidence_text = json.dumps(semantic(context['subject']), ensure_ascii=False) + '\n' + '\n'.join(
            (s['evidence'].get('excerpt') or '') + '\n' + (s['evidence'].get('section') or '') for s in context['sources'])
        if any(quote not in evidence_text for quote in benchmark['evidence_quotes']):
            raise ContractError('Benchmark quote is absent from supplied evidence')
        if not isinstance(result['reasons'], list):
            raise ContractError('Reasons must be a list')
        result['reasons'].extend('%s: %s' % (field, '; '.join(benchmark[field]) if isinstance(benchmark[field], list) else benchmark[field]) for field in sorted(fields))
    return result


def make_assessment(context, rules, result, at, previous=None, model_id=None,
                    revisit=None, evaluator=None, revision=None):
    ih = input_hash(context, rules, model_id, revisit)
    aid = 'assessment-' + digest([key(context), ih, previous['assessment_id'] if previous else None])[:32]
    result = dict(result)
    result.update(schema_version=2, assessment_id=aid, subject_kind=context['subject_kind'],
                  subject_id=context['subject_id'], input_hash=ih, input_revision=revision,
                  rule_version=rules['rule_version'], evaluator=evaluator or ('model' if model_id else 'deterministic'),
                  model_id=model_id, prompt_version=rules['prompt_version'], assessed_at=at,
                  supersedes=previous['assessment_id'] if previous else None,
                  evidence_source_item_ids=[s['source_item_id'] for s in context['sources']])
    validate_record('assessment', result)
    if result['status'] == 'selected' and (not result['comparison_question'] or not result['priority'] or result['benchmark_readiness'] == 'unknown'):
        raise ContractError('Selection needs a comparison question, priority and benchmark conditions')
    return result


def latest_assessments(assessments, as_of=None):
    eligible = [a for a in assessments if as_of is None or timestamp(a['assessed_at']) <= timestamp(as_of)]
    superseded = {a['supersedes'] for a in eligible if a['supersedes']}
    heads = {}
    for assessment in eligible:
        if assessment['assessment_id'] not in superseded:
            if key(assessment) in heads:
                raise ContractError('Assessment history has multiple heads for one subject')
            heads[key(assessment)] = assessment
    return heads


def legacy_records(repository, dataset, contexts, rules, at):
    """Import real original judgments once, without claiming a fresh evaluation."""
    root = Path(repository)
    existing = {key(a) for a in dataset['assessment']}
    imported = []
    for event in dataset['feature_event']:
        if ('feature_event', event['event_id']) in existing:
            continue
        archive = root / 'data/event-revisions' / event['event_id'] / 'schema-v1.json'
        provenance = None
        if archive.exists():
            original = json.loads(archive.read_text())
            provenance = str(archive.relative_to(root))
        else:
            original = None
            for path in sorted((root / 'experiments/chrome/monthly').glob('*.json')):
                value = json.loads(path.read_text())
                if isinstance(value, dict):
                    original = next((e for e in value.get('events', []) if e.get('event_id') == event['event_id'] and e.get('selection_status')), None)
                if original:
                    provenance = str(path.relative_to(root)) + '#event_id=' + event['event_id']
                    break
        if not original or not original.get('selection_status'):
            continue
        context = contexts[('feature_event', event['event_id'])]
        result = decision(original['selection_status'], original.get('selection_reason') or 'Legacy judgment has no written reason.',
                          priority=original.get('priority'), question=original.get('comparison_question'),
                          readiness=original.get('benchmark_readiness', 'unknown'), revisit=original.get('revisit_trigger'))
        if original.get('priority_reason'):
            result['reasons'].append('Original priority reason: ' + original['priority_reason'])
        result['reasons'].append('Imported legacy judgment; no new PM evaluation. Provenance: ' + provenance)
        assessment = make_assessment(context, rules, result, original.get('assessed_at') or at,
                                     evaluator='legacy', revision=provenance + ':sha256:' + digest(original))
        assessment['rule_version'] = original.get('selection_rule_version') or 'legacy-unversioned'
        assessment['prompt_version'] = None
        assessment['evidence_source_item_ids'] = list(event['source_item_ids'])
        imported.append(assessment)
    for source in dataset['source_item']:
        if not source['item_key'].startswith('flag-document:') or ('source_item', source['source_item_id']) in existing:
            continue
        flag = source['item_key'].split(':', 1)[1]
        path = root / 'experiments/chrome' / (flag + '.md')
        if not path.exists():
            continue
        document = path.read_text()
        pending = 'PM 선별은 검증 대기입니다.' in document
        explicit = re.findall(r'판정:\s*(selected|watch|pending_verification|excluded)[ .·/]([^\n]*)', document)
        # A Markdown paragraph is not enough to reconstruct a selected benchmark.
        # Import only explicit nonselected decisions; selection needs structured provenance.
        if not pending and (not explicit or explicit[-1][0] == 'selected'):
            continue
        context = contexts.get(('source_item', source['source_item_id'])) or {
            'subject_kind': 'source_item', 'subject_id': source['source_item_id'],
            'subject': source, 'sources': [source], 'catalog': None}
        result = decision('pending_verification' if pending else explicit[-1][0],
                          'PM 선별은 검증 대기입니다.' if pending else explicit[-1][1].strip(),
                          revisit='Review public user impact, benchmark task and current registration evidence.')
        provenance = str(path.relative_to(root))
        result['reasons'].append('Imported legacy flag-document judgment. Original assessment time and rule version are unknown; assessed_at records import time. Provenance: ' + provenance)
        assessment = make_assessment(context, rules, result, at, evaluator='legacy',
                                     revision=provenance + ':sha256:' + hashlib.sha256(path.read_bytes()).hexdigest())
        assessment['rule_version'], assessment['prompt_version'] = 'legacy-unversioned', None
        imported.append(assessment)
    return imported


def link_item(context, assessment):
    kind = context['subject_kind']
    catalog = context['catalog']
    return {'subject_kind': kind, 'subject_id': context['subject_id'],
            'assessment_id': assessment['assessment_id'],
            'catalog_id': (catalog.get('feature_id') or catalog.get('experiment_id')) if catalog else None,
            'event_ids': [context['subject_id']] if kind.endswith('_event') else [],
            'experiment_kind': context['subject'].get('experiment_kind')}


def project(dataset, contexts, assessments, rules, at, as_of=None):
    """Current cards use the newest assessed event of each owner, even if excluded.

    An unassessed/failed new event does not erase the last good selected card.
    Historical event assessments stay accessible and are never rewritten.
    """
    heads = latest_assessments(assessments, as_of)
    active = {}
    for k, assessment in heads.items():
        if k not in contexts:
            continue
        context = contexts[k]
        item = link_item(context, assessment)
        owner = item['catalog_id'] or k
        rank = event_time(context['subject']) if k[0].endswith('_event') else (timestamp(assessment['assessed_at']), k[1])
        if owner not in active or rank > active[owner][0]:
            active[owner] = rank, item, assessment
    outputs = {}
    for selection_kind in ('features', 'flags'):
        previous = next((s for s in dataset['selected'] if s['selection_kind'] == selection_kind), None)
        history = copy.deepcopy(previous['history']) if previous else []
        old_ids = {h['assessment_id'] for h in history}
        seen_selected = {key(h) for h in history if h['action'] != 'deselected'}
        by_id = {a['assessment_id']: a for a in assessments}
        for assessment in sorted(assessments, key=lambda a: (timestamp(a['assessed_at']), a['assessment_id'])):
            if as_of and timestamp(assessment['assessed_at']) > timestamp(as_of):
                continue
            k = key(assessment)
            if k not in contexts or assessment['assessment_id'] in old_ids:
                continue
            item = link_item(contexts[k], assessment)
            if (item['experiment_kind'] is not None) != (selection_kind == 'flags'):
                continue
            prior = by_id.get(assessment['supersedes'])
            if assessment['status'] != 'selected' and (not prior or prior['status'] != 'selected'):
                continue
            action = 'deselected' if assessment['status'] != 'selected' else ('changed' if prior and prior['status'] == 'selected' else ('reselected' if k in seen_selected else 'selected'))
            change = dict(item, change_id='selection-' + digest([selection_kind, assessment['assessment_id'], action])[:32],
                          previous_assessment_id=assessment['supersedes'], action=action, effective_at=assessment['assessed_at'])
            history.append(change)
            if action != 'deselected':
                seen_selected.add(k)
        history.sort(key=lambda h: (timestamp(h['effective_at']), h['change_id']))
        if as_of:
            history = [h for h in history if timestamp(h['effective_at']) <= timestamp(as_of)]
        current = sorted([item for _, item, a in active.values() if a['status'] == 'selected' and
                          (item['experiment_kind'] is not None) == (selection_kind == 'flags')], key=lambda r: key(r))
        result = {'schema_version': 2, 'selection_kind': selection_kind, 'as_of': as_of or at,
                  'input_hash': digest([current, history]), 'rule_version': rules['rule_version'],
                  'current': current, 'history': history}
        if policy(dataset, as_of):
            result['collection_scope'] = policy(dataset, as_of)
            result['input_hash'] = digest([current, history, result['collection_scope']])
        if previous and previous['input_hash'] == result['input_hash'] and not as_of:
            result = copy.deepcopy(previous)
        validate_record('selected', result)
        if previous and not as_of:
            validate_transition('selected', previous, result)
        outputs[selection_kind] = result
    return outputs


def run(repository, private_dir, *, assessed_at, rules=None, provider=None, model_id=None,
        revisit=None, dry_run=False):
    """Evaluate all principal subjects, retain successes, publish one valid graph.

    provider(context, rules) returns exactly the decision keys, plus
    evidence_source_item_ids. Exceptions/invalid results produce private failures.
    revisit is a subject-ID -> explicit trigger token mapping; the token is hashed.
    """
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    if private == root or root in private.parents:
        raise ValueError('Evaluation operations must stay outside the repository')
    if bool(provider) != bool(model_id):
        raise ValueError('An injected provider and explicit model_id are required together')
    timestamp(assessed_at)
    rules = rules or load_rules()
    state_path = private / 'selection-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    effective_revisit = state.get('revisit_tokens', {})
    effective_revisit.update(revisit or {})
    revisit = effective_revisit
    dataset = load_dataset(root)
    contexts, coverage = build_contexts(dataset)
    imported = legacy_records(root, dataset, contexts, rules, assessed_at)
    assessments = copy.deepcopy(dataset['assessment']) + imported
    heads = latest_assessments(assessments)
    imported_keys = {key(a) for a in imported}
    created, failures, cached = [], [], 0
    for k, context in sorted(contexts.items()):
        previous = heads.get(k)
        token = revisit.get(k[1])
        evaluator_model = model_id if eligible(context) else None
        ih = input_hash(context, rules, evaluator_model, token)
        if previous and (previous['input_hash'] == ih or (k in imported_keys and token is None and provider is None and context_scope(context) is None)):
            cached += 1
            continue
        try:
            if not eligible(context):
                result = evaluate(context, rules)
            elif provider:
                result = provider_decision(provider(copy.deepcopy(context), copy.deepcopy(rules)), context)
            else:
                result = evaluate(context, rules)
            assessment = make_assessment(context, rules, result, assessed_at, previous,
                                         evaluator_model, token, revision='semantic-v2-sha256:' + digest(semantic(context['subject'])))
            if previous and timestamp(assessment['assessed_at']) < timestamp(previous['assessed_at']):
                raise ContractError('Assessment time precedes the previous judgment')
            assessments.append(assessment)
            created.append(assessment)
        except Exception as error:
            # Error details can contain provider data. They never enter public JSON.
            failures.append({'state': 'evaluation_failed', 'subject_kind': k[0], 'subject_id': k[1],
                             'input_hash': ih, 'error_type': type(error).__name__})
    selected = project(dataset, contexts, assessments, rules, assessed_at)
    replacements = {}
    for a in imported + created:
        path = 'data/assessments/%s/%s.json' % (a['subject_kind'], a['assessment_id'])
        if (root / path).exists() and json.loads((root / path).read_text()) != a:
            raise ContractError('Assessment records are immutable')
        replacements[path] = a
    for kind, value in selected.items():
        if failures and not assessments and not dataset['selected']:
            continue
        replacements['data/selected/%s/current.json' % kind] = value
        # Versioned dated snapshots are below an archive level, outside current globs.
        path = 'data/selected/history/%s/%s-%s.json' % (assessed_at[:10], kind, value['input_hash'])
        if not (root / path).exists():
            replacements[path] = value
    # PM compatibility fields are derived only from actual new evaluations.
    updates = {a['subject_id']: a for a in created if a['subject_kind'] == 'feature_event'}
    for path in root.glob(PATHS['feature_event']):
        value = json.loads(path.read_text())
        changed = False
        for event in records(value):
            assessment = updates.get(event['event_id'])
            if assessment and event.get('origin') == 'legacy':
                event.update(selection_status=assessment['status'], selection_reason=' '.join(assessment['reasons']),
                             priority=assessment['priority'], priority_reason=assessment['reasons'][0] if assessment['priority'] else None,
                             comparison_question=assessment['comparison_question'], benchmark_readiness=assessment['benchmark_readiness'],
                             revisit_trigger=assessment['revisit_trigger'], assessed_at=assessment['assessed_at'], selection_rule_version=assessment['rule_version'])
                changed = True
        if changed:
            replacements[str(path.relative_to(root))] = value
    validate_graph(root, replacements)
    if not dry_run:
        publish(root, replacements, private / 'publication')
    private.mkdir(parents=True, exist_ok=True)
    operation = {'assessed_at': assessed_at, 'created': len(created), 'imported': len(imported),
                 'cached': cached, 'failures': failures, 'coverage': {sid: list(k) for sid, k in coverage.items()},
                 'principal_subjects': len(contexts), 'source_items': len(coverage)}
    (private / 'selection-result.json').write_text(json.dumps(operation, ensure_ascii=False, indent=2) + '\n')
    if not dry_run:
        state_path.write_text(json.dumps({'revisit_tokens': revisit}, indent=2) + '\n')
    return {'created': created, 'imported': imported, 'cached': cached, 'failures': failures,
            'selected': selected, 'coverage': coverage, 'replacements': replacements}


def as_of(repository, cutoff, rules=None):
    dataset = load_dataset(repository)
    contexts, _ = build_contexts(dataset)
    return project(dataset, contexts, dataset['assessment'], rules or load_rules(), cutoff, as_of=cutoff)


def catalog_transitions(repository, previous_cutoff, cutoff):
    """Return owner replacements, distinct from same-subject PM status changes.

    These are derived comparison records, not schema-v2 selection changes. T6
    must not pass them off as deselection assessments of historical subjects.
    """
    dataset = load_dataset(repository)
    contexts, _ = build_contexts(dataset)

    def state(at):
        result = {}
        for k, assessment in latest_assessments(dataset['assessment'], at).items():
            if k not in contexts:
                continue
            context = contexts[k]
            item = link_item(context, assessment)
            if not item['catalog_id']:
                continue
            rank = event_time(context['subject']) if k[0].endswith('_event') else (timestamp(assessment['assessed_at']), k[1])
            owner = item['catalog_id']
            if owner not in result or rank > result[owner][0]:
                result[owner] = rank, dict(item, status=assessment['status'], assessed_at=assessment['assessed_at'])
        return {owner: row for owner, (_, row) in result.items()}

    before, after = state(previous_cutoff), state(cutoff)
    return [{'transition_id': 'catalog-transition-' + digest([owner, before[owner], after[owner]])[:32],
             'kind': 'catalog_subject_replaced', 'catalog_id': owner,
             'previous': before[owner], 'current': after[owner]}
            for owner in sorted(set(before) & set(after))
            if key(before[owner]) != key(after[owner]) and
            'selected' in (before[owner]['status'], after[owner]['status'])]
