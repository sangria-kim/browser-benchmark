"""Check the first accepted receipt through ordinary commits and every merge parent."""
from datetime import datetime, timezone
from functools import lru_cache
import json
import subprocess

from pipeline import browser_status, daily_status, weekly_status, weekly_evidence
from pipeline.temporal import instant, policy_day
from pipeline.run_daily import git, repository_head

FOLDERS = (daily_status.FOLDER, weekly_status.FOLDER, browser_status.FOLDER)
FOLDER_NAMES = frozenset(path.split('/')[1] for path in FOLDERS)
EMPTY = (None, None)


def canonical_paths(rel):
    """Return the receipt pair for a representable cutoff, or None for any other name."""
    if not rel.isascii():
        return None
    try:
        if daily_status.status_path(rel):
            day = rel.rsplit('/', 1)[1][:-5]
            return rel, browser_status.detail_path('daily', day + 'T07:00:00+09:00')
        weekly = weekly_status.is_receipt(rel)
        if weekly or browser_status.is_detail(rel):
            name = rel.rsplit('/', 1)[1]
            stamp = datetime.strptime(name, '%Y-%m-%dT%H%M%S.%fZ.json').replace(tzinfo=timezone.utc)
            local = stamp.astimezone(daily_status.KST)
            if weekly or '/weekly_reconcile/' in rel:
                return f'{weekly_status.FOLDER}/{name}', f'{browser_status.FOLDER}/weekly_reconcile/{name}'
            day, _ = daily_status.receipt(local.isoformat(), None, None)
            return day, rel
    except (ValueError, OverflowError):
        # A date-shaped name can still be an impossible instant or outside the local calendar.
        return None
    return None


def paths_for(rel):
    pair = canonical_paths(rel)
    if pair is None:
        raise ValueError('Invalid receipt path: ' + rel)
    return pair


def check_spelling(names, reserved):
    for name in names:
        if name.casefold() in reserved and name not in reserved:
            raise ValueError('Invalid spelling of reserved receipt directory: ' + name)


def direct_git_children(root, tree):
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-z', tree])
    children = {}
    for entry in raw.split(b'\0'):
        if entry:
            info, name = entry.split(b'\t', 1)
            mode, kind, oid = info.split()
            children[name.decode('utf-8', 'surrogateescape')] = (mode, kind, oid)
    return children


@lru_cache(maxsize=64)
def tracked_paths(root, head):
    # Literal Git pathspecs can miss a differently cased prefix. Inspect the
    # immediate names, independently of the checkout filesystem's case rules.
    top = direct_git_children(root, head)
    check_spelling(top, {'data'})
    if 'data' in top:
        _, kind, oid = top['data']
        if kind != b'tree':
            raise ValueError('Invalid committed data directory')
        check_spelling(direct_git_children(root, oid), FOLDER_NAMES)
    entries = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', head, '--', *FOLDERS])
    tracked = set()
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        info, name = entry.split(b'\t', 1)
        mode, kind, _ = info.split()
        rel = name.decode('ascii', 'surrogateescape')
        paths_for(rel)
        if kind != b'blob' or mode not in (b'100644', b'100755'):
            raise ValueError('Invalid committed receipt file: ' + rel)
        tracked.add(rel)
    return frozenset(tracked)


def advance(paths, prior, current):
    """A candidate must retain every previously accepted result on this branch."""
    whole, detail = prior
    new_whole, new_detail = current
    if whole and not new_whole:
        raise ValueError('Committed collection receipt is missing: ' + paths[0])
    if detail and not new_detail:
        raise ValueError('Committed browser detail is missing: ' + paths[1])
    if whole and daily_status.status_path(paths[0]):
        old = json.loads(whole)
        if old['status'] == 'complete' and (new_whole != whole or new_detail and not detail):
            raise ValueError('Cannot change a completed daily status or add browser outcomes')
        if json.loads(new_whole)['cutoff'] != old['cutoff']:
            raise ValueError('This date already has a different daily cutoff')
    elif whole and new_whole != whole:
        raise ValueError('Cannot change an accepted whole weekly result')
    if detail:
        browser_status.transition(json.loads(detail), json.loads(new_detail))


def validate_snapshot(paths, current):
    whole, detail = (json.loads(raw) if raw is not None else None for raw in current)
    daily = daily_status.status_path(paths[0])
    if current[0] is not None:
        if daily:
            daily_status.validate_receipt(paths[0], whole)
        else:
            weekly_status.validate(paths[0], whole)
    if current[1] is not None:
        browser_status.validate_detail(paths[1], detail)
        if daily:
            _, expected = daily_status.receipt(detail['scope']['cutoff'], *browser_status.aggregate(detail))
            if whole != expected:
                raise ValueError('Daily aggregate differs from browser outcomes')
        elif whole is not None:
            raise ValueError('Conflicting whole and browser weekly publications')


@lru_cache(maxsize=256)
def weekly_aliases(root, ref, paths):
    """Find signed receipt proposals for this cutoff, including deleted aliases."""
    spellings = {name.casefold() + suffix: name for name in paths for suffix in ('', '.bak')}
    # Git's icase is narrower than Unicode casefold. Match the cutoff in the
    # two reserved directories, then check the complete spelling in Python.
    stamp = paths[0].rsplit('/', 1)[1].removesuffix('.json')
    specs = [':(icase,glob)data/' + folder + '/' + stamp + '.*'
             for folder in ('wee*', 'brow*/wee*')]
    raw = subprocess.check_output(['git', '-C', str(root), 'log', '--raw', '--no-abbrev', '--root', '-m',
                                   '--full-history', '--no-renames', '-z', '--format=', ref, '--', *specs])
    fields = iter(raw.split(b'\0'))
    candidates = set()
    for header in fields:
        if not header:
            continue
        name = next(fields).decode('utf-8', 'surrogateescape')
        canonical = spellings.get(name.casefold())
        if canonical is None or name in paths:
            continue
        old_mode, new_mode, old_oid, new_oid, _ = header.strip().lstrip(b':').split()
        for mode, oid in ((old_mode, old_oid), (new_mode, new_oid)):
            if mode in (b'100644', b'100755'):
                candidates.add((canonical, mode, oid))
    proposals = set()
    for rel, mode, oid in candidates:
        raw = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])
        validate = weekly_status.validate if rel == paths[0] else browser_status.validate_detail
        try:
            validate(rel, json.loads(raw))
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            continue  # A file with a backup suffix alone does not establish a submission.
        proposals.add((rel, mode, oid))
    return proposals


def require_committed_repair(root, ref, paths, tracked):
    if (ref and weekly_status.is_receipt(paths[0]) and not tracked.intersection(paths)
            and paths[0] >= weekly_status.path(weekly_status.FIRST_GUARDED_CUTOFF)
            and weekly_aliases(root, ref, paths)):
        raise ValueError('Restore the original publication in a commit before saving this weekly cutoff')


def has_receipt_alias(root, commit, rel, oid):
    # Only an exact regular blob at the corresponding case alias or backup
    # spelling can identify the original submission. Other files establish nothing.
    *folders, filename = rel.split('/')
    trees = [(commit, False)]
    for component in folders:
        trees = [(child, changed or name != component)
                 for tree, changed in trees
                 for name, (_, kind, child) in direct_git_children(root, tree).items()
                 if kind == b'tree' and name.casefold() == component.casefold()]
    for tree, changed in trees:
        for name, (mode, _, child) in direct_git_children(root, tree).items():
            if (child == oid and mode in (b'100644', b'100755') and (changed or name != filename)
                    and name.casefold() in {filename.casefold(), filename.casefold() + '.bak'}):
                return True
    return False


def data_roots(root, commit):
    return {name: entry for name, entry in direct_git_children(root, commit).items() if name.casefold() == 'data'}


def prior_tree_state(root, folder, original, restored, rel, oid):
    """Identify an empty receipt slot or the exact original alias in the otherwise identical tree."""
    if original == restored:
        return 'alias' if folder != 'data' else None
    diff = subprocess.check_output(['git', '-C', str(root), 'diff-tree', '-r', '-z', '--raw', '--no-renames',
                                    '--abbrev=64', original[2], restored[2]])
    fields = diff.split(b'\0')
    # An absent marker produces one addition. Renaming its alias produces one
    # addition and one deletion. Any other change is outside this repair.
    if len(fields) not in (3, 5) or fields[-1]:
        return None
    added_mode = None
    removed_mode = None
    canonical = rel.encode()
    for index in range(0, len(fields) - 1, 2):
        header, path = fields[index:index + 2]
        old_mode, new_mode, old_oid, new_oid, status = header.split()
        old_mode = old_mode.removeprefix(b':')
        if status == b'A' and new_oid == oid and b'data/' + path == canonical and added_mode is None:
            added_mode = new_mode
        elif status == b'D' and old_oid == oid and removed_mode is None:
            alias = folder.encode() + b'/' + path
            folded = alias.decode('utf-8', 'surrogateescape').casefold()
            if alias == canonical or folded not in (rel.casefold(), rel.casefold() + '.bak'):
                return None
            removed_mode = old_mode
        else:
            return None
    if added_mode not in (b'100644', b'100755'):
        return None
    if removed_mode is None:
        return 'gap'
    return 'alias' if removed_mode == added_mode else None


def prior_deleted_aliases(root, restored, parent, ancestry, rel, oid):
    """Trace all parents through verifiable gaps until each reaches the exact first submission."""
    if len(ancestry[restored]) != 1:
        return set()
    destination = data_roots(root, restored)
    if set(destination) != {'data'} or destination['data'][1] != b'tree':
        return set()
    expected = destination['data']
    sources = set()
    pending = [parent]
    visited = set()
    while pending:
        revision = pending.pop()
        if revision in visited:
            continue
        visited.add(revision)
        entries = data_roots(root, revision)
        if len(entries) > 1:
            return set()
        if entries:
            folder, original = next(iter(entries.items()))
            if original[1] != b'tree':
                return set()
            state = prior_tree_state(root, folder, original, expected, rel, oid)
            if state == 'alias':
                sources.add((revision, original))
                continue
            if state != 'gap':
                return set()
        # Either all data is absent or the only missing file is this receipt.
        if not ancestry[revision]:
            return set()
        pending.extend(ancestry[revision])
    return sources


def first_weekly_submission(root, rel, commit, ancestry, scope, registry, first_parents, inherited, allow_continuation=False):
    info = git(root, 'ls-tree', commit, '--', rel).split()
    proposal = (rel, info[0].encode(), info[2].encode())
    oid = proposal[2]
    paths = paths_for(rel)
    since, cutoff = policy_day(scope['start']), instant(scope['cutoff'])
    pending = [(commit, None)]
    seen = set()
    while pending:
        child, original_tree = pending.pop()
        if (child, original_tree) in seen:
            continue
        seen.add((child, original_tree))
        parents = first_parents if child == commit else ancestry[child]
        continuing = False
        for parent in parents:
            earlier = weekly_aliases(root, parent, paths)
            if earlier - {proposal}:
                raise ValueError('An earlier weekly receipt conflicts with the original publication')
            if earlier and has_receipt_alias(root, parent, rel, oid):
                if original_tree is not None and list(data_roots(root, parent).values()) != [original_tree]:
                    raise ValueError('The original weekly submission differs from the restored data tree')
                weekly_evidence.check_alias_transition(root, parent, child, since, cutoff)
                pending.append((parent, original_tree))
                continuing = True
            else:
                if earlier:
                    # The same proposal may have been deleted even when its count was zero.
                    # Prove its complete data tree and use its original policy.
                    sources = prior_deleted_aliases(root, child, parent, ancestry, rel, oid)
                    if not sources:
                        raise ValueError('Cannot verify the original publication across the deleted weekly receipt')
                    pending.extend(sources)
                    continuing = True
                else:
                    weekly_evidence.check_committed(root, parent, since, cutoff)
        if not continuing and (child != commit or not inherited):
            browser_status.check_registry(root, scope, facts=registry(child, scope['mode']), registry_ref=child,
                                          continuing=allow_continuation and child == commit)


def check_publication_policy(root, files, candidate, prior, commit, registry, reviewed, ancestry, first_parents):
    # Each cutoff has at most one scoped receipt or whole weekly marker.
    index = 1 if candidate[1] is not None else 0
    raw = candidate[index]
    if raw is None or daily_status.status_path(files[index]):
        return
    record = json.loads(raw)
    inherited = any(old[index] is not None and json.loads(old[index]) == record for old in prior)
    scope = record['scope']
    continuing = index == 1 and any(old[1] is not None and json.loads(old[1])['scope'] == scope for old in prior)
    if (scope['mode'] == 'weekly_reconcile' and weekly_status.guarded(scope['cutoff'])
            and (first_parents or not ancestry[commit])):
        # Receiving the other parent's accepted marker is still a first
        # settlement on a side that had no marker. Inspect that side's evidence.
        first_weekly_submission(root, files[index], commit, ancestry, scope, registry, first_parents, inherited, continuing)
        return
    if inherited:
        return  # The existing result can retain the policy under which it was authored.
    if (reviewed and index == 1 and scope['mode'] == 'weekly_reconcile'
            and not any(old[1] for old in prior) and not weekly_status.guarded(scope['cutoff'])):
        raise ValueError('New unmarked historical weekly browser result has no authoritative base')
    browser_status.check_registry(root, scope, facts=registry(commit, scope['mode']),
                                  continuing=continuing, registry_ref=commit)


def changed_groups(root, commits, pathspec):
    # Feed all parent edges to one tree diff. Git echoes non-object lines, which
    # mark the child even when several parents have different receipt trees.
    requests = []
    for child, parents in commits:
        requests.append('commit ' + child)
        requests.extend(child + ' ' + parent for parent in parents)
        if not parents:
            requests.append(child)
    output = subprocess.check_output(
        ['git', '-C', str(root), '-c', 'core.quotePath=true', 'diff-tree', '--stdin', '--root', '-r', '--no-renames',
         '--no-commit-id', '--name-only', '--', *pathspec],
        input=('\n'.join(requests) + '\n').encode()).decode()
    groups = {}
    for line in output.splitlines():
        if line.startswith('commit '):
            child = line.split()[1]
        else:
            # Only canonical paths can establish authority. A rename still reports
            # deletion of the canonical source because rename detection is off.
            files = canonical_paths(line)
            if files is not None:
                groups.setdefault(files, set()).add(child)
    return groups


def verify_publication(root, rel):
    verify(root, paths=paths_for(rel), complete_history=True)


def verify(root, *, base=None, paths=(), complete_history=False):
    head = repository_head(root)
    if paths:  # Writers, including no-op retries, must also reject present-day invalid names.
        _, _, tracked = browser_status.receipt_inventory(root, head)
    if not head:
        if base:
            raise ValueError('Receipt comparison needs an existing Git commit')
        return
    shallow_file = root / git(root, 'rev-parse', '--git-path', 'shallow')
    shallow = frozenset(shallow_file.read_text().splitlines()) if shallow_file.exists() else frozenset()
    verify_commits(root, head, base, tuple(paths), shallow, complete_history)
    if paths:
        require_committed_repair(root, head, tuple(paths), tracked)


@lru_cache(maxsize=64)
def verify_commits(root, head, base, paths, shallow, complete_history):
    if base:
        if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', base, head]).returncode:
            raise ValueError('Cannot establish receipt ancestry from the comparison commit; fetch full history')
    def walk(*excluded):
        revisions = git(root, 'rev-list', '--reverse', '--topo-order', '--parents', head, *excluded)
        return [(fields[0], fields[1:]) for line in revisions.splitlines() if (fields := line.split())]

    reviewed = set()
    if base:
        batch = walk('^' + base)
        reviewed = {child for child, _ in batch}
        if reviewed & shallow:
            raise ValueError('Incomplete receipt ancestry; fetch full history')
        if not reviewed and shallow and not complete_history:
            # A local shallow data checkout can validate its working tree against HEAD.
            return
    # CI checks all receipt paths even when this push changes none of them.
    # Local writers pass only the two paths that belong to their cutoff.
    commits = walk()
    if (base or complete_history) and any(child in shallow for child, _ in commits):
        raise ValueError('Incomplete receipt ancestry; fetch full history')
    if not commits:
        return

    @lru_cache(maxsize=None)
    def blob(oid):
        return subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])

    @lru_cache(maxsize=None)
    def snapshot(commit, files):
        found = {}
        for line in git(root, 'ls-tree', commit, '--', *files).splitlines():
            info, path = line.split('\t', 1)
            mode, kind, oid = info.split()
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise ValueError('Invalid committed receipt file: ' + path)
            found[path] = blob(oid)
        return tuple(found.get(path) for path in files)

    @lru_cache(maxsize=None)
    def registry(commit, mode):
        raw, = snapshot(commit, ('config/sources.yml',))
        if raw is None:
            raise ValueError('Missing registry at receipt publication')
        return browser_status.registry_snapshot(raw, mode)

    ancestry = dict(commits)
    for files, changed in changed_groups(root, commits, paths or FOLDERS).items():
        authorities = {}
        last_error = None
        for child, parents in commits:
            prior = set()
            for parent in parents:
                prior.update(authorities[parent])
            if not prior:
                prior.add(EMPTY)
            if child in changed:
                try:
                    candidate = snapshot(child, files)
                    validate_snapshot(files, candidate)
                    for previous in prior:
                        advance(files, previous, candidate)
                    if child not in shallow:
                        first_parents = [p for p in parents if EMPTY in authorities[p]]
                        check_publication_policy(root, files, candidate, prior, child, registry,
                                                 child in reviewed, ancestry, first_parents)
                    prior = {candidate}
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
                    # A later ordinary commit can restore the accepted record. A bad
                    # proposal cannot replace the constraints inherited by that repair.
                    last_error = str(error)
            authorities[child] = prior
        final = snapshot(head, files)
        if authorities[head] != {final}:
            raise ValueError(last_error or 'Committed receipt history conflicts with the final result: ' + files[0])
