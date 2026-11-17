"""Copy verified response evidence into a new run, never status or output records."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from .collector import atomic_json


def seed_cache(source, destination, cutoff):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Cache handoff requires a new destination')
    destination.parent.mkdir(parents=True, exist_ok=True)
    provenance = {'cutoff': cutoff, 'sources': {}, 'blobs': {}}
    with tempfile.TemporaryDirectory(prefix='.cache-handoff-', dir=destination.parent) as temp:
        stage = Path(temp) / 'browser'
        (stage / 'cache').mkdir(parents=True)
        for path in sorted(source.glob('*-progress.json')):
            if path.is_symlink():
                raise ValueError('Cache progress must be a regular file')
            progress_bytes = path.read_bytes()
            data = json.loads(progress_bytes)
            if data['cutoff'] != cutoff:
                raise ValueError('Cache handoff cutoff mismatch')
            responses = data['responses']
            for url, entry in responses.items():
                sha = entry['sha256']
                if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                    raise ValueError('Invalid cached response hash')
                blob = source / 'cache' / sha
                if blob.is_symlink() or not blob.is_file():
                    raise ValueError('Cache blob must be a regular file')
                raw = blob.read_bytes()
                if hashlib.sha256(raw).hexdigest() != sha:
                    raise ValueError('Cache handoff checksum mismatch')
                (stage / 'cache' / sha).write_bytes(raw)
                provenance['blobs'][sha] = len(raw)
            # Every document is re-parsed by the new frozen code. Completion,
            # errors, public records, and prior parser judgments are not copied.
            atomic_json(stage / path.name, {'cutoff': cutoff, 'responses': responses, 'documents': []})
            provenance['sources'][path.name] = hashlib.sha256(progress_bytes).hexdigest()
        if not provenance['sources']:
            raise ValueError('No response cache to carry forward')
        shutil.move(str(stage), str(destination))
    return provenance
