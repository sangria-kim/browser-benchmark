"""Check the first accepted receipt through ordinary commits and every merge parent."""
from datetime import datetime, timezone
from functools import lru_cache
import json
import subprocess

from pipeline import browser_status, daily_status, weekly_status
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
            _, kind, oid = info.split()
            children[name.decode('utf-8', 'surrogateescape')] = (kind, oid)
    return children


@lru_cache(maxsize=64)
def tracked_paths(root, head):
    # Literal Git pathspecs can miss a differently cased prefix. Inspect the
    # immediate names, independently of the checkout filesystem's case rules.
    top = direct_git_children(root, head)
    check_spelling(top, {'data'})
    if 'data' in top:
        kind, oid = top['data']
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


def check_publication_policy(root, files, candidate, prior, commit, registry, reviewed):
    # Each cutoff has at most one scoped receipt or whole weekly marker.
    index = 1 if candidate[1] is not None else 0
    raw = candidate[index]
    if raw is None or daily_status.status_path(files[index]):
        return
    record = json.loads(raw)
    if any(old[index] is not None and json.loads(old[index]) == record for old in prior):
        return  # A merge or repair can inherit a result authored under an earlier policy.
    scope = record['scope']
    if (reviewed and index == 1 and scope['mode'] == 'weekly_reconcile'
            and not any(old[1] for old in prior) and not weekly_status.guarded(scope['cutoff'])):
        raise ValueError('New unmarked historical weekly browser result has no authoritative base')
    browser_status.check_registry(root, scope, facts=registry(commit, scope['mode']))


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
        browser_status.receipt_inventory(root, head)
    if not head:
        if base:
            raise ValueError('Receipt comparison needs an existing Git commit')
        return
    shallow_file = root / git(root, 'rev-parse', '--git-path', 'shallow')
    shallow = frozenset(shallow_file.read_text().splitlines()) if shallow_file.exists() else frozenset()
    verify_commits(root, head, base, tuple(paths), shallow, complete_history)


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
                        check_publication_policy(root, files, candidate, prior, child, registry, child in reviewed)
                    prior = {candidate}
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
                    # A later ordinary commit can restore the accepted record. A bad
                    # proposal cannot replace the constraints inherited by that repair.
                    last_error = str(error)
            authorities[child] = prior
        final = snapshot(head, files)
        if authorities[head] != {final}:
            raise ValueError(last_error or 'Committed receipt history conflicts with the final result: ' + files[0])
