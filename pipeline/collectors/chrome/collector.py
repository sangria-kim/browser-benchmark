"""Pinned experiment collection and private, versioned normalization handoff."""
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from collections.abc import Mapping

from schemas.validate import validate_record, validate_transition
from .parser import parse, auxiliary_definitions, strip_comments, safe_excerpt, literal, masked, Candidate, references as expression_references
from .parser import feature_state_definitions, conditions_at, impossible_conditions, arguments, IDENT
from .providers import atomic_json, canonical, digest, private_directory, safe_path
from .generated import blink_features, PATHS as BLINK_PATHS, INPUT as BLINK_INPUT
from .generated import network_switches, NETWORK_LIST, NETWORK_DEFINITION
from .generated import MOJO_GENERATOR, mojo_missing_default_is_disabled


PARSER_VERSION = 'chromium-lexical-v2'
PARSER_SHA256 = digest(b'\n'.join((Path(__file__).parent / name).read_bytes()
                                for name in ('collector.py', 'parser.py', 'generated.py')))
REGISTRIES = {'chrome/browser/about_flags.cc', 'ios/chrome/browser/flags/about_flags.mm'}


class SourceTexts(Mapping):
    """Keep the pinned manifest in memory, not the entire Chromium text tree."""
    def __init__(self, hashes, read):
        self.hashes, self.read = hashes, read

    def __iter__(self):
        return iter(self.hashes)

    def __len__(self):
        return len(self.hashes)

    def __getitem__(self, path):
        if path not in self.hashes:
            raise KeyError(path)
        raw = self.read(path)
        if digest(raw) != self.hashes[path]:
            raise ValueError('Source changed after manifest: ' + path)
        return raw.decode('utf-8')


def identity(prefix, value):
    return prefix + '-' + digest(canonical(value))[:24]


def in_scope(path, config):
    discovery = config['discovery']
    parts = Path(path).parts
    return (not set(parts).intersection(discovery['exclude_path_components'])
            and any(root == '.' or path == root or path.startswith(root.rstrip('/') + '/') for root in discovery['roots'])
            and Path(path).suffix in discovery['extensions'])


def read_metadata(files):
    metadata, never, expired, errors = {}, set(), {}, []
    for path in files:
        if not path.endswith(('/flag-metadata.json', '/flag-never-expire-list.json', '/expired_flags_list.h')):
            continue
        text = files[path]
        try:
            if path.endswith('/flag-metadata.json'):
                for item in json.loads(strip_comments(text)):
                    name, expiry = item['name'], item['expiry_milestone']
                    if not isinstance(name, str) or not isinstance(expiry, int) or expiry < -1:
                        raise ValueError('Invalid metadata')
                    metadata[name] = expiry
            elif path.endswith('/flag-never-expire-list.json'):
                data = json.loads(strip_comments(text))
                if not isinstance(data, list) or not all(isinstance(v, str) for v in data):
                    raise ValueError('Invalid never-expire list')
                never.update(data)
            elif path.endswith('/expired_flags_list.h'):
                for name, milestone in re.findall(r'\{\s*"([^"\n]+)"\s*,\s*(\d+)\s*\}', strip_comments(text)):
                    expired[name] = int(milestone)
        except (ValueError, KeyError, TypeError):
            errors.append({'path': path, 'reason': 'invalid_expiry_metadata'})
    major = re.search(r'^MAJOR=(\d+)$', files.get('chrome/VERSION', ''), re.M)
    return metadata, never, expired, int(major[1]) if major else None, errors


def collect(config, provider, state_dir, *, observed_at=None, origin='baseline',
            sample_paths=None, max_files=None, max_trees=None, previous=None):
    """Return {source_items, experiments, facts, coverage, revision}.

    state_dir must be outside this repository. Passing sample_paths explicitly
    selects partial sampling. Budgets never imply complete coverage. Existing
    source histories can be supplied with previous or loaded from private state.
    All failures leave prior records intact. No PM selection occurs here.
    """
    validate_record('chrome_scope_config', config)
    state_dir = private_directory(state_dir)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    # Resume a fixed revision across calls when a named run state already exists.
    checkpoint = state_dir / 'checkpoint.json'
    saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if saved and saved['scope_sha256'] != digest(canonical(config)):
        raise ValueError('Use a new state directory for a different scope')
    if saved and hasattr(provider, 'ref'):
        provider.ref = saved['revision']
    revision = provider.pin()
    if saved and revision != saved['revision']:
        raise ValueError('Resume revision changed; use a new state directory')
    atomic_json(checkpoint, {'revision': revision, 'scope_sha256': digest(canonical(config)), 'parser_version': PARSER_VERSION})
    errors, hashes = [], {}
    if sample_paths is not None:
        listing = {'paths': sorted(set(map(safe_path, sample_paths))), 'complete': False, 'unsupported': []}
    else:
        try:
            listing = provider.enumerate(state_dir, max_trees=max_trees)
        except Exception as exc:
            listing = {'paths': [], 'complete': False, 'unsupported': []}
            errors.append({'stage': 'enumerate', 'reason': str(exc)})
    paths = set(listing['paths'])
    missing = sorted(set(config['required_paths']) - paths) if sample_paths is None and listing['complete'] else []
    # Fetch required paths even before a large tree traversal has completed.
    selected = sorted(p for p in paths if in_scope(p, config) or p in config['optional_paths'] or p in config['required_paths'])
    selected = sorted(set(config['required_paths']) | set(selected))
    pending = []
    downloaded = 0
    cache = state_dir / 'blobs' / revision
    local = getattr(provider, 'pinned_local', False)
    def read_source(path):
        return provider.read(path) if local else (cache / path).read_bytes()
    for path in selected:
        cached = cache / path
        try:
            if local:
                raw = provider.read(path)
            elif cached.exists():
                raw = cached.read_bytes()
            else:
                if max_files is not None and downloaded >= max_files:
                    pending.append(path)
                    continue
                raw = provider.read(path)
                downloaded += 1
                cached.parent.mkdir(parents=True, exist_ok=True)
                temp = cached.with_name(cached.name + '.tmp')
                temp.write_bytes(raw)
                temp.replace(cached)
            raw.decode('utf-8')
            hashes[path] = digest(raw)
        except Exception as exc:
            errors.append({'path': path, 'reason': str(exc)})
    files = SourceTexts(hashes, read_source)
    candidates, declaration_count, auxiliary, imports = [], 0, {}, {}
    mojo_default_disabled = mojo_missing_default_is_disabled(files)
    for path, text in files.items():
        if Path(path).suffix not in config['discovery']['extensions']:
            continue
        parsed, declarations, issues = parse(path, text, mojo_default_disabled=mojo_default_disabled)
        imports[path] = re.findall(r'\busing\s+((?:[A-Za-z_]\w*::)+k[A-Z]\w*)\s*;', masked(text))
        candidates.extend(parsed)
        declaration_count += len(declarations)
        errors.extend({'path': path, 'reason': issue} for issue in issues)
        for symbol, values in auxiliary_definitions(text).items():
            auxiliary.setdefault(symbol, []).extend(dict(v, path=path) for v in values)
    metadata, never, expired, milestone, metadata_errors = read_metadata(files)
    generated, generator_errors = blink_features(files)
    candidates.extend(generated)
    errors.extend({'path': BLINK_INPUT, 'reason': issue} for issue in generator_errors)
    generated, generator_errors = network_switches(files)
    candidates.extend(generated)
    errors.extend({'path': NETWORK_LIST, 'reason': issue} for issue in generator_errors)
    errors.extend(metadata_errors)
    if 'chrome/VERSION' in files and milestone is None:
        errors.append({'path': 'chrome/VERSION', 'reason': 'invalid_version'})
    # A registry with no recognized table must never count as a successful parse.
    for path in REGISTRIES.intersection(files):
        if not any(c.path == path and c.kind == 'flag_entry' for c in candidates):
            errors.append({'path': path, 'reason': 'missing_flag_table'})

    def names(ref, path, namespace):
        if ref.startswith('::'):
            return [ref[2:]]
        imported = [v for v in imports.get(path, []) if v.split('::')[-1] == ref]
        if imported:
            return sorted(set(imported))
        parts = namespace.split('::') if namespace else []
        return ['::'.join(parts[:i] + [ref]) for i in range(len(parts), -1, -1)]

    def auxiliary_values(ref, path, namespace=''):
        for qualified in names(ref, path, namespace):
            values = [v for v in auxiliary.get(ref.split('::')[-1], [])
                      if (v['namespace'] + '::' if v['namespace'] else '') + ref.split('::')[-1] == qualified]
            local = [v for v in values if v['path'] == path]
            if values:
                return local or values
        return []

    # Symbolic registry IDs (for example kEnableBenchmarking) are resolved
    # only from an unambiguous string definition. Unsupported names stay raw.
    for c in candidates:
        if c.kind == 'flag_entry' and c.value is None and not c.symbol.startswith('unresolved-'):
            values = auxiliary_values(c.symbol, c.path, c.namespace)
            if len(values) == 1 and values[0]['value'] is not None:
                c.symbol = c.value = values[0]['value']
            else:
                c.parsed = False
    registered_names = {c.symbol for c in candidates if c.kind == 'flag_entry'}
    metadata_path = 'chrome/browser/flag-metadata.json'
    for name in sorted(set(metadata) - registered_names):
        # A metadata-only entry is evidence of a source flag, not of UI exposure.
        # Reconstruct only the two allowlisted fields. Never copy an owner row.
        expression = json.dumps({'name': name, 'expiry_milestone': metadata[name]}, sort_keys=True)
        match = re.search(r'"name"\s*:\s*' + re.escape(json.dumps(name)), files.get(metadata_path, ''))
        line = files[metadata_path].count('\n', 0, match.start()) + 1 if match else 1
        candidates.append(Candidate('flag_entry', name, metadata_path, line, line, expression,
                                    parsed=True, value=name, registered=False))
    keyed, occurrence = [], {}
    for c in candidates:
        base = [c.kind, c.path, c.qualified_symbol, c.conditions]
        key = canonical(base).decode()
        ordinal = occurrence.get(key, 0)
        occurrence[key] = ordinal + 1
        stable = base + [ordinal]
        keyed.append((c, canonical(stable).decode(), identity('src-chromium', stable), identity('exp-chromium', stable)))
    symbol_index = {}
    candidate_by_id = {eid: c for c, _, _, eid in keyed}
    for c, _, _, eid in keyed:
        if c.kind != 'flag_entry':
            symbol_index.setdefault(c.qualified_symbol, []).append((c, eid))

    def resolve(ref, candidate):
        # Qualified symbols must match their namespace. Bare references are
        # local to the same namespace; ambiguity is kept unresolved.
        matches = next((symbol_index[n] for n in names(ref, candidate.path, candidate.namespace) if n in symbol_index), [])
        local = [(c, eid) for c, eid in matches if c.path == candidate.path]
        matches = local or matches
        if len(matches) == 1:
            return [matches[0][1]]
        # Separate conditional arms in one definition file are a known symbol
        # family. Keep every target and its own build conditions. Cross-file
        # ambiguity remains unresolved rather than selecting an arbitrary arm.
        if matches and len({c.path for c, _ in matches}) == 1 and len({tuple(c.conditions) for c, _ in matches}) == len(matches):
            return [eid for _, eid in matches]
        return []

    def expand(refs, path, namespace, seen=None):
        seen = set() if seen is None else seen
        result = []
        for ref in refs:
            seen_key = (ref, path, namespace)
            if seen_key in seen:
                continue
            seen.add(seen_key)
            values = auxiliary_values(ref, path, namespace)
            if len(values) == 1:
                value = values[0]
                result.append({'symbol': ref, 'path': value['path'], 'expression': value['expression']})
                result.extend(expand(value['refs'], value['path'], value['namespace'], seen))
        return result

    state_definitions, condition_cache, local_macros = {}, {}, {}

    def macro_names(path):
        if path not in local_macros:
            text = strip_comments(files[path])
            local_macros[path] = set(re.findall(r'^\s*#\s*(?:define|undef)[ \t]+([A-Za-z_]\w*)(?!\w|\()', text, re.M))
        return local_macros[path]

    def condition_macros(path, conditions):
        # BUILDFLAG platform predicates stay symbolic. A locally defined bare
        # condition macro can change meaning without changing the guard text;
        # do not claim that its unevaluated condition is unchanged.
        if not conditions:
            return []
        tokens = set(re.findall(r'\b[A-Za-z_]\w*\b', re.sub(r'BUILDFLAG\s*\(\s*\w+\s*\)', '', ' '.join(conditions))))
        return ['condition macro: ' + name for name in sorted(tokens & macro_names(path))]

    def initializer_conditions(value):
        key = value['path'], value['path_line']
        if key not in condition_cache:
            text = strip_comments(files[value['path']])
            offset = sum(len(line) for line in text.splitlines(keepends=True)[:value['path_line'] - 1])
            condition_cache[key] = conditions_at(text, offset)
        return condition_cache[key]

    def initializer(expression, path, namespace, conditions, kind='state', seen=(), line=None):
        expression = expression.strip()
        terminal = r'(?:(?:base::)?FeatureState::|base::)?FEATURE_(?:ENABLED|DISABLED)_(?:BY_DEFAULT|FOR_COUNTRIES)'
        if kind == 'name' and literal(expression) is not None or kind == 'state' and re.fullmatch(terminal, expression):
            return [], []
        parts = arguments(expression)
        if kind == 'state' and len(parts) > 1:
            if not all(literal(part) is not None for part in parts[1:]):
                return [], [expression]
            return initializer(parts[0], path, namespace, conditions, kind, seen, line)
        if not re.fullmatch(IDENT, expression) or (expression, path, namespace) in seen:
            return [], [expression]
        if path not in state_definitions:
            state_definitions[path] = feature_state_definitions(files[path])
        values = auxiliary_values(expression, path, namespace)
        macros = [dict(v, path=path) for v in state_definitions[path].get(expression.split('::')[-1], []) if v.get('macro')]
        if expression.split('::')[-1] in macro_names(path):
            # No C++ preprocessor implementation is implied. Macro/constant
            # collisions, undef/redefinition ordering and qualified replacement
            # are unsupported instead of being silently resolved to one body.
            if (values or any(not v.get('macro') for v in state_definitions[path].get(expression, []))
                    or '::' in expression or not macros or re.search(r'^\s*#\s*undef[ \t]+' + re.escape(expression) + r'\b', files[path], re.M)):
                return [], [expression]
            values = [v for v in macros if line is None or v['path_line'] < line]
        elif not values:
            for qualified in names(expression, path, namespace):
                values = [dict(v, path=path) for v in state_definitions[path].get(expression.split('::')[-1], [])
                          if not v.get('macro') and '::'.join(filter(None, (v['namespace'], expression.split('::')[-1]))) == qualified]
                if values:
                    break
        if not values or len({v['path'] for v in values}) != 1:
            return [], [expression]
        values = [v for v in values if not impossible_conditions(conditions + initializer_conditions(v))]
        guards = [initializer_conditions(v) for v in values]
        # Multiple definitions must be mutually exclusive and cover the
        # feature's own build conditions. Ambiguous/missing arms stay unknown.
        if (not values or any(not impossible_conditions(conditions + left + right)
                              for i, left in enumerate(guards) for right in guards[i + 1:])
                or not impossible_conditions(conditions + ['!(' + ' || '.join(
                    '(' + ' && '.join('(' + c + ')' for c in guard) + ')' if guard else '1' for guard in guards) + ')'])):
            return [], [expression]
        options, unresolved = [], []
        for value, guard in zip(values, guards):
            options.append(dict(symbol=expression, path=value['path'], expression=value['expression'], conditions=guard))
            unresolved.extend(condition_macros(value['path'], guard))
            nested, missing = initializer(value['expression'], value['path'], namespace if value.get('macro') else value['namespace'], conditions + guard,
                                          kind, seen + ((expression, path, namespace),), line if value.get('macro') else value['path_line'])
            options.extend(nested); unresolved.extend(missing)
        return options, unresolved

    bundle_path = state_dir / 'handoff.json'
    prior = previous if previous is not None else (json.loads(bundle_path.read_text()) if bundle_path.exists() else {})
    old_items = {r['source_item_id']: r for r in prior.get('source_items', [])}
    old_experiments = {r['experiment_id']: r for r in prior.get('experiments', [])}
    old_facts = {r['source_item_id']: r for r in prior.get('facts', [])}
    source_items, experiments, facts = [], [], []
    input_failure = bool(errors or pending or missing or (set(config['required_paths']) - set(files)))
    preserved_ids = set()
    current_unresolved_reference_count = 0
    incomplete_tree = not listing['complete'] or sample_paths is not None
    old_facts_by_experiment = {f['experiment_id']: f for f in old_facts.values()}

    def prior_dependency_paths(fact, visited=None):
        # Follow the persisted dependency graph, including known relationships.
        # Infer paths for older v1 bundles that predate explicit dependencies.
        visited = set() if visited is None else visited
        eid = fact['experiment_id']
        if eid in visited:
            return set()
        visited.add(eid)
        result = {d['path'] for d in fact.get('dependencies', [])}
        result.add(fact['definition']['path'])
        result.update(option['path'] for option in fact['semantic']['options'])
        result.update(loc['path'] for loc in old_experiments.get(eid, {}).get('source_locations', []))
        for reference in fact['semantic']['references']:
            target = old_facts_by_experiment.get(reference['target_id'])
            if target:
                result.update(prior_dependency_paths(target, visited))
        return result
    for c, key, sid, eid in keyed:
        refs = [(ref, c) for ref in c.refs]
        options = expand(c.refs, c.path, c.namespace)
        for option in options:
            # Resolve an initializer's bare names in its own lexical namespace,
            # not the namespace of the flag that refers to the initializer.
            values = [v for v in auxiliary.get(option['symbol'].split('::')[-1], [])
                      if v['path'] == option['path'] and v['expression'] == option['expression']]
            context = copy.copy(c)
            context.path = option['path']
            context.namespace = values[0]['namespace'] if len(values) == 1 else ''
            refs.extend((ref, context) for ref in expression_references(option['expression']))
        references, unresolved = [], condition_macros(c.path, c.conditions)
        if c.kind == 'base_feature' and c.path != BLINK_INPUT and c.default:
            defaults, missing_defaults = initializer(c.default, c.path, c.namespace, c.conditions, line=c.line)
            options.extend(defaults)
            unresolved.extend(missing_defaults)
        if c.value_ref:
            values, missing_values = initializer(c.value_ref, c.path, c.namespace, c.conditions, 'name', line=c.line)
            options.extend(values)
            unresolved.extend(missing_values)
        seen_refs = set()
        for ref, context in refs:
            ref_key = (ref, context.path, context.namespace)
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)
            targets = resolve(ref, context)
            if targets:
                references.extend({'kind': 'alias_of' if ref == c.alias else 'controls', 'target_id': target}
                                  for target in targets if target != eid)
            elif not auxiliary_values(ref, context.path, context.namespace):
                unresolved.append(ref)
        references = list({(r['kind'], r['target_id']): r for r in references}.values())
        current_unresolved_reference_count += len(unresolved)
        old = old_items.get(sid)
        old_fact = old_facts.get(sid)
        old_experiment = old_experiments.get(eid)
        degraded = bool(not c.parsed and old and old['record_status'] == 'parsed')
        if old_fact:
            old_semantic = old_fact['semantic']
            newly_unresolved = set(unresolved) - set(old_semantic['unresolved_references'])
            lost_references = ({(r['kind'], r['target_id']) for r in old_semantic['references']} -
                               {(r['kind'], r['target_id']) for r in references})
            lost_options = ({(o['symbol'], o['path']) for o in old_semantic['options']} -
                            {(o['symbol'], o['path']) for o in options})
            missing_dependencies = prior_dependency_paths(old_fact) - set(files)
            lost_descriptions = any(ref and literal(ref) is None and old_semantic[field] and
                                    not auxiliary_values(ref, c.path, c.namespace)
                                    for field, ref in (('title', c.title_ref), ('description', c.description_ref)))
            degraded = degraded or bool(newly_unresolved) or bool(incomplete_tree and
                (lost_references or lost_options or missing_dependencies or lost_descriptions))

        if old and old_fact and old_experiment and (input_failure or degraded):
            # A failed auxiliary read is not a fact change. Keep all three
            # materializations together, including their original source revision.
            # Current raw observations remain in the private pinned blob cache.
            source_items.append(copy.deepcopy(old))
            experiments.append(copy.deepcopy(old_experiment))
            facts.append(copy.deepcopy(old_fact))
            preserved_ids.add(eid)
            continue
        if input_failure:
            # A new candidate still gets a minimal public source record. Do not
            # promote unavailable auxiliary values into active/default facts.
            c.parsed = False

        exp = metadata.get(c.symbol) if c.kind == 'flag_entry' else None
        never_expire = (c.symbol in never or exp == -1) if c.kind == 'flag_entry' else None
        lifecycle = 'active'
        if c.kind == 'flag_entry' and not never_expire and (c.symbol in expired or (exp is not None and milestone is not None and exp <= milestone)):
            lifecycle = 'expired'
        if input_failure:
            lifecycle, exp, never_expire = 'unknown', None, None
            references, options = [], []
        definition_default = None if input_failure else c.default
        def description(ref):
            if ref is None:
                return None
            if literal(ref) is not None:
                return safe_excerpt(literal(ref))
            values = auxiliary_values(ref, c.path, c.namespace)
            if len(values) == 1 and values[0]['value']:
                return safe_excerpt(values[0]['value'])
            return None
        title = safe_excerpt(description(c.title_ref) or c.value or c.symbol)
        summary = description(c.description_ref)
        semantic = {'kind': c.kind, 'symbol': c.qualified_symbol, 'definition': c.expression,
                    'conditions': c.conditions, 'default': definition_default, 'value': c.value,
                    'platforms': c.platforms, 'expiry_milestone': exp, 'never_expire': never_expire,
                    'lifecycle': lifecycle, 'references': references, 'unresolved_references': unresolved,
                    'options': options, 'registered': c.registered, 'title': title, 'description': summary, 'parsed': c.parsed}
        semantic_hash = digest(canonical(semantic))
        evidence = {'url': config['repository_url'] + '/+/' + revision + '/' + c.path + '#L' + str(c.line),
                    'section': c.path + ':' + str(c.line), 'source_revision': revision,
                    'content_sha256': semantic_hash, 'observed_at': observed_at, 'excerpt': safe_excerpt(c.expression)}
        row = {'schema_version': 2, 'source_item_id': sid, 'source_id': config['source_id'], 'browser': 'chrome',
               'item_key': key, 'item_type': c.kind, 'title': title, 'summary': summary,
               'channel': 'unknown', 'platform': c.platforms or ['unknown'], 'version': None,
               'published_at': None, 'observed_at': observed_at, 'evidence': evidence,
               'record_status': 'parsed' if c.parsed else 'unparsed', 'origin': origin,
               'lifecycle': 'unknown' if input_failure else 'active', 'experiment_kind': c.kind, 'source_location': c.path + ':' + str(c.line),
               'source_symbol': c.qualified_symbol, 'revisions': []}
        old = old_items.get(sid)
        if old and old['evidence']['source_revision'] == revision and old['evidence']['content_sha256'] == semantic_hash:
            row = copy.deepcopy(old)
        else:
            row['revisions'] = copy.deepcopy(old['revisions']) if old else []
            snapshot = {k: row[k] for k in ('title', 'summary', 'evidence', 'published_at', 'observed_at')}
            snapshot.update(revision_id=identity('rev', [sid, revision, semantic_hash]), content_sha256=semantic_hash, source_revision=revision)
            row['revisions'].append(snapshot)
            if old:
                validate_transition('source_item', old, row)
        experiment = {'schema_version': 2, 'experiment_id': eid, 'experiment_kind': c.kind, 'canonical_key': key,
                      'symbol': c.qualified_symbol, 'flag_id': c.symbol if c.kind == 'flag_entry' else None,
                      'title': title, 'description': summary, 'source_item_ids': [sid], 'event_ids': [],
                      'source_locations': [{'path': c.path, 'revision': revision, 'line_start': c.line,
                                            'line_end': c.end_line, 'content_sha256': hashes[c.path]}],
                      'build_conditions': c.conditions, 'platform': c.platforms or ['unknown'],
                      'default_state': definition_default, 'expiry_milestone': exp, 'never_expire': never_expire,
                      'ui_exposure': 'registered' if c.registered else 'unknown',
                      'product_channel': None, 'product_revision': None, 'installed_availability': 'unknown',
                      'verification_status': 'source_only', 'lifecycle': lifecycle,
                      'relationships': references, 'aliases': [], 'legacy': False}
        if c.kind == 'flag_entry':
            for evidence_path in ('chrome/browser/flag-metadata.json', 'chrome/browser/flag-never-expire-list.json', 'chrome/browser/expired_flags_list.h', 'chrome/VERSION'):
                if evidence_path in hashes and evidence_path != c.path:
                    experiment['source_locations'].append({'path': evidence_path, 'revision': revision, 'line_start': None, 'line_end': None, 'content_sha256': hashes[evidence_path]})
        dependency_paths = {c.path}
        if c.path == BLINK_INPUT:
            dependency_paths.update(BLINK_PATHS)
        if c.path == NETWORK_LIST:
            dependency_paths.add(NETWORK_DEFINITION)
        if c.path.endswith('.mojom') and mojo_default_disabled:
            dependency_paths.add(MOJO_GENERATOR)
        dependency_paths.update(option['path'] for option in options)
        if c.kind == 'flag_entry':
            dependency_paths.update(path for path in config['required_paths'] if path in hashes)
        for description_ref in (c.title_ref, c.description_ref):
            if description_ref and literal(description_ref) is None:
                dependency_paths.update(v['path'] for v in auxiliary_values(description_ref, c.path, c.namespace))
        for reference in references:
            target = candidate_by_id.get(reference['target_id'])
            if target:
                dependency_paths.add(target.path)
        fact = {'bundle_version': 1, 'source_item_id': sid, 'experiment_id': eid,
                'source_revision': revision, 'semantic_sha256': semantic_hash, 'file_sha256': hashes[c.path],
                'definition': asdict(c), 'semantic': semantic,
                'dependencies': [{'path': path, 'content_sha256': hashes[path]}
                                 for path in sorted(dependency_paths) if path in hashes]}
        validate_record('source_item', row)
        validate_record('experiment', experiment)
        source_items.append(row)
        experiments.append(experiment)
        facts.append(fact)
    unparsed = sum(not c.parsed for c in candidates)
    unsupported_in_scope = [p for p in listing['unsupported'] if in_scope(p, config) or p in config['required_paths']]
    unresolved_reference_count = current_unresolved_reference_count
    complete = bool(not unresolved_reference_count and not unsupported_in_scope and listing['complete'] and not missing and not errors and not pending and not unparsed and sample_paths is None)
    # Source absence proves deletion only between two complete same-scope trees.
    # Otherwise retain all earlier items without asserting a removed lifecycle.
    old_complete = prior.get('coverage', {}).get('complete', False)
    removed = []
    current_ids = {r['source_item_id'] for r in source_items}
    for sid in sorted(set(old_items) - current_ids):
        row = copy.deepcopy(old_items[sid])
        experiment = copy.deepcopy(next((e for e in old_experiments.values() if sid in e['source_item_ids']), None))
        fact = copy.deepcopy(old_facts.get(sid))
        if complete and old_complete and prior.get('scope_sha256') == digest(canonical(config)):
            # Keep prior definition evidence. A deletion proof is a separate
            # structured diff input for T4, not a fabricated source excerpt.
            removed.append({'source_item_id': sid, 'experiment_id': experiment['experiment_id'] if experiment else None,
                            'before_revision': row['evidence']['source_revision'], 'after_revision': revision,
                            'proof': 'absent_from_complete_pinned_tree', 'scope_sha256': digest(canonical(config))})
            row['lifecycle'] = 'removed'
            if experiment:
                experiment['lifecycle'] = 'removed'
            if fact:
                fact['removal'] = removed[-1]
        source_items.append(row)
        if experiment:
            experiments.append(experiment)
        if fact:
            facts.append(fact)
    registered_targets = {rel['target_id'] for e in experiments if e['experiment_kind'] == 'flag_entry' for rel in e['relationships']}
    for experiment in experiments:
        if experiment['experiment_id'] in preserved_ids:
            continue
        if not complete and experiment['experiment_id'] in old_experiments:
            experiment['ui_exposure'] = old_experiments[experiment['experiment_id']]['ui_exposure']
            continue
        if experiment['experiment_kind'] == 'flag_entry' and experiment['ui_exposure'] == 'unknown' and complete:
            experiment['ui_exposure'] = 'not_registered'
        if experiment['experiment_kind'] != 'flag_entry':
            experiment['ui_exposure'] = 'registered' if experiment['experiment_id'] in registered_targets else ('not_registered' if complete else 'unknown')
    coverage = {'complete': complete, 'mode': 'sample' if sample_paths is not None else 'full_tree',
                'tree_complete': listing['complete'], 'tracked_paths': len(paths), 'fetched_files': len(files),
                'candidate_count': len(candidates), 'parsed_count': len(candidates) - unparsed, 'unparsed_count': unparsed,
                'unresolved_reference_count': unresolved_reference_count, 'declarations_or_type_uses': declaration_count, 'missing_required_paths': missing,
                'enumeration_complete': bool(listing['complete'] and not missing and not pending),
                'parsing_complete': bool(not unparsed and not errors and not pending),
                'retained_semantic_ids': sorted(preserved_ids), 'pending_paths': pending, 'errors': errors, 'unsupported_tree_entries': listing['unsupported'], 'unsupported_in_scope': unsupported_in_scope}
    result = {'bundle_version': 1, 'parser_version': PARSER_VERSION, 'parser_sha256': PARSER_SHA256, 'revision': revision,
              'scope_sha256': digest(canonical(config)), 'source_items': sorted(source_items, key=lambda x: x['source_item_id']),
              'experiments': sorted(experiments, key=lambda x: x['experiment_id']),
              'facts': sorted(facts, key=lambda x: x['source_item_id']), 'removed_candidates': removed, 'coverage': coverage}
    atomic_json(state_dir / 'manifest.json', {'revision': revision, 'paths': sorted(paths), 'sha256': hashes})
    atomic_json(bundle_path, result)
    return result
