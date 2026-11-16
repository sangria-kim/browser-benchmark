"""Pinned, injectable source providers. Caches and traversal journals are private."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import quote
from urllib.request import urlopen, Request


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def private_directory(path, repository=None):
    path = Path(path).resolve()
    repository = Path(repository or Path(__file__).resolve().parents[3]).resolve()
    if path == repository or repository in path.parents:
        raise ValueError('State must be outside the public repository')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def safe_path(path):
    p = PurePosixPath(path)
    if not path or p.is_absolute() or '..' in p.parts or '\\' in path:
        raise ValueError('Unsafe repository path')
    return path


class LocalCheckout:
    """Read the entire tracked tree from an unchanged, clean checkout at HEAD."""
    pinned_local = True
    def __init__(self, path, revision='HEAD'):
        self.path = Path(path).resolve()
        self.ref = revision
        self.revision = None
        self.blob_ids = {}

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.path)] + list(args), stderr=subprocess.PIPE)

    def pin(self):
        if self.git('status', '--porcelain', '--untracked-files=all').strip():
            raise ValueError('Chromium checkout must be clean')
        revision = self.git('rev-parse', '--verify', self.ref + '^{commit}').decode().strip()
        if revision != self.git('rev-parse', 'HEAD').decode().strip():
            raise ValueError('Checkout HEAD must match pinned revision')
        self.revision = revision
        return revision

    def enumerate(self, state_dir, max_trees=None):
        if not self.revision:
            raise ValueError('Pin before enumeration')
        entries, unsupported = [], []
        for row in self.git('ls-tree', '-rz', '--full-tree', self.revision).split(b'\0'):
            if not row:
                continue
            metadata, raw_path = row.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split()
            path = safe_path(raw_path.decode('utf-8'))
            if kind == 'blob' and mode != '120000':
                entries.append(path)
                self.blob_ids[path] = oid
            else:
                unsupported.append(path)
        return {'paths': sorted(entries), 'complete': True, 'unsupported': unsupported}

    def read(self, path):
        if not self.revision:
            raise ValueError('Pin before read')
        path = safe_path(path)
        # Sparse checkouts may omit unrelated files. A materialized source is
        # accepted only when its Git blob ID matches the pinned tracked tree.
        # This avoids a subprocess for every one of >100,000 source files.
        local = self.path / path
        if path in self.blob_ids and local.is_file() and not local.is_symlink():
            raw = local.read_bytes()
            oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if oid != self.blob_ids[path]:
                raise ValueError('Checkout blob differs from pinned revision: ' + path)
            return raw
        return self.git('show', self.revision + ':' + path)


class Gitiles:
    def __init__(self, repository_url, ref='refs/heads/main', transport=None):
        self.url = repository_url.rstrip('/')
        self.ref = ref
        self.revision = None
        self.transport = transport or self.fetch

    @staticmethod
    def fetch(url):
        with urlopen(Request(url, headers={'User-Agent': 'browser-benchmark-source/1.0'}), timeout=60) as response:
            return response.read()

    def json(self, url):
        raw = self.transport(url).decode('utf-8')
        return json.loads(raw.split('\n', 1)[1] if raw.startswith(")]}'") else raw)

    def pin(self):
        if re.fullmatch('[0-9a-f]{40}', self.ref):
            # Verify that a caller-supplied hash resolves to an actual commit.
            ref = self.ref
        else:
            ref = quote(self.ref, safe='/')
        data = self.json(self.url + '/+/' + ref + '?format=JSON')
        revision = data.get('commit')
        if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('Gitiles ref did not resolve to a commit')
        if re.fullmatch('[0-9a-f]{40}', self.ref) and revision != self.ref:
            raise ValueError('Gitiles returned another commit')
        self.revision = revision
        return revision

    def enumerate(self, state_dir, max_trees=None):
        if not self.revision:
            raise ValueError('Pin before enumeration')
        journal = Path(state_dir) / (self.revision + '-tree.json')
        state = json.loads(journal.read_text()) if journal.exists() else {
            'revision': self.revision, 'repository': self.url, 'pending': [''], 'visited': [], 'paths': [], 'unsupported': []}
        if state['revision'] != self.revision or state['repository'] != self.url:
            raise ValueError('Traversal journal identity mismatch')
        steps = 0
        while state['pending'] and (max_trees is None or steps < max_trees):
            path = state['pending'][0]
            data = self.json(self.url + '/+/' + self.revision + '/' + quote(path, safe='/') + '?format=JSON')
            # Current Gitiles trees are unpaged. Refuse unknown page/truncation
            # markers rather than silently claiming exhaustion.
            if any(data.get(k) for k in ('next', 'nextPageToken', 'next_page_token', 'truncated')):
                raise ValueError('Unsupported tree pagination or truncation')
            if not isinstance(data.get('entries'), list):
                raise ValueError('Malformed Gitiles tree')
            new_paths, children, unsupported = [], [], []
            for entry in data['entries']:
                name = entry.get('name', '')
                if '/' in name or name in ('.', '..'):
                    raise ValueError('Malformed Gitiles entry')
                child = safe_path(path + name)
                if entry.get('type') == 'tree':
                    children.append(child + '/')
                elif entry.get('type') == 'blob' and entry.get('mode') not in (40960, '120000'):
                    new_paths.append(child)
                else:
                    unsupported.append(child)
            state['paths'].extend(new_paths)
            state['unsupported'].extend(unsupported)
            state['visited'].append(path)
            state['pending'] = sorted(set(state['pending'][1:] + children) - set(state['visited']))
            atomic_json(journal, state)
            steps += 1
        return {'paths': sorted(set(state['paths'])), 'complete': not state['pending'],
                'unsupported': state['unsupported']}

    def read(self, path):
        if not self.revision:
            raise ValueError('Pin before read')
        return base64.b64decode(self.transport(self.url + '/+/' + self.revision + '/' + quote(safe_path(path), safe='/') + '?format=TEXT'), validate=True)
