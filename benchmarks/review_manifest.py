"""Canonical real-work review snapshot; frozen benchmark patch digests remain unchanged.

Usage: python3 benchmarks/review_manifest.py --base <recorded commit> [--repo .]
Use --path once per task path when unrelated work is present. Store output outside the
checkout. Compare --staged and --revision HEAD with the same base/paths to review (hooks included).
"""
import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path


def _git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def canonical_manifest(repo, base, paths=None, *, staged=False, revision=None):
    repo = Path(repo).resolve()
    base = _git(repo, 'rev-parse', '--verify', base + '^{commit}').decode().strip()
    names = lambda raw: [os.fsdecode(p) for p in raw.split(b'\0') if p]
    if staged and revision is not None:
        raise ValueError('select either index or revision, not both')
    if revision is not None:
        revision = _git(repo, 'rev-parse', '--verify', revision + '^{commit}').decode().strip()
    diff_args = (['--cached'] if staged else []) + [base] + ([revision] if revision else [])
    changed = names(_git(repo, 'diff', '--no-renames', '--name-only', '-z', *diff_args))
    new = names(_git(repo, 'ls-files', '--others', '--exclude-standard', '-z')) if not staged and not revision else []
    selected = sorted(set(changed + new if paths is None else paths))
    def read_tree(ref):
        return _git(repo, 'ls-tree', '-rz', ref).split(b'\0')

    def parse_tree(entries):
        tree = {}
        for entry in entries:
            if not entry:
                continue
            metadata, path = entry.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split()
            tree[os.fsdecode(path)] = {'mode': mode, 'kind': kind, 'oid': oid}
        return tree

    tree = parse_tree(read_tree(base))
    target = parse_tree(read_tree(revision)) if revision else None
    if staged:
        target = {}
        for entry in _git(repo, 'ls-files', '--stage', '-z').split(b'\0'):
            if not entry:
                continue
            metadata, path = entry.split(b'\t', 1)
            mode, oid, stage = metadata.decode().split()
            if stage != '0':
                raise ValueError('unmerged index cannot be approved')
            target[os.fsdecode(path)] = {'mode': mode, 'kind': 'commit' if mode == '160000' else 'blob', 'oid': oid}
    files = []
    for name in selected:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or name != relative.as_posix() or name == '.':
            raise ValueError('task paths must be normalized repository-relative file paths')
        path = repo / relative
        for parent in relative.parents:
            if (repo / parent).is_symlink():
                raise ValueError('refusing a task path below a symlink: ' + name)
        before = tree.get(name)
        if before and before['kind'] != 'blob':
            raise ValueError('submodule/tree requires separate review: ' + name)
        if target is not None:
            entry = target.get(name)
            if entry is None:
                after = None
            elif entry['kind'] != 'blob':
                raise ValueError('submodule/tree requires separate review: ' + name)
            else:
                content = _git(repo, 'cat-file', 'blob', entry['oid'])
                after = {'mode': entry['mode'], 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        else:
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                after = None
            else:
                if stat.S_ISLNK(mode):
                    content, git_mode = os.fsencode(os.readlink(path)), '120000'
                elif stat.S_ISREG(mode):
                    content = path.read_bytes()
                    git_mode = '100755' if mode & 0o111 else '100644'
                else:
                    raise ValueError('task path is not a regular file or symlink: ' + name)
                after = {'mode': git_mode, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        files.append({'path': name, 'before': before, 'after': after})
    manifest = {'format': 'task-change-manifest-1', 'base': base, 'files': files}
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return {'manifest': manifest, 'digest': hashlib.sha256(encoded).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--base', required=True)
    parser.add_argument('--path', action='append', dest='paths')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--staged', action='store_true')
    source.add_argument('--revision', help='committed tree to verify, e.g. HEAD')
    args = parser.parse_args()
    print(json.dumps(canonical_manifest(args.repo, args.base, args.paths, staged=args.staged, revision=args.revision), indent=2))
