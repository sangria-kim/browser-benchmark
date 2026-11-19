"""Read regular data blobs from a pinned Git tree."""
import subprocess

from schemas.validate import ContractError


def git(repository, *args):
    return subprocess.check_output(['git', '-C', str(repository), *args], stderr=subprocess.PIPE)


def git_tree(repository, sha):
    result = {}
    for entry in git(repository, 'ls-tree', '-r', '-z', sha).split(b'\0'):
        if not entry:
            continue
        header, path = entry.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        result[path.decode('utf-8')] = (mode, kind, oid)
    return result


def read_blobs(repository, entries):
    """One Git process; immutable object IDs prevent branch movement mixing bytes."""
    process = subprocess.Popen(['git', '-C', str(repository), 'cat-file', '--batch'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for path, (mode, kind, oid) in sorted(entries.items()):
            if mode != '100644' or kind != 'blob':
                raise ContractError('Only non-executable regular data files are allowed: ' + path)
            process.stdin.write((oid + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3 or header[0] != oid or header[1] != 'blob':
                raise ContractError('Invalid Git blob response')
            size = int(header[2])
            data = process.stdout.read(size)
            if len(data) != size or process.stdout.read(1) != b'\n':
                raise ContractError('Truncated Git blob')
            yield path, data
    finally:
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
        process.wait()
