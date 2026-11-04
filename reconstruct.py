#!/usr/bin/env python3
"""Reconstruct SAT2024 from verified ASCII parts (Python 3 standard library)."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile

BLOCK = 1024 * 1024


def checksum_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def checksums(path):
    rows = []
    for line in path.read_text(encoding='ascii').splitlines():
        digest, name = line.split('  ', 1)
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid checksum in ' + str(path))
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or str(p) != name:
            raise ValueError('unsafe checksum path: ' + name)
        rows.append((digest, name))
    if len({name for _, name in rows}) != len(rows):
        raise ValueError('duplicate checksum paths')
    return rows


def main():
    if len(sys.argv) > 2:
        raise ValueError('usage: reconstruct.sh [existing-destination-parent]')
    here = Path(__file__).resolve().parent
    parent = Path(sys.argv[1] if len(sys.argv) == 2 else os.getcwd()).resolve()
    if not parent.is_dir():
        raise ValueError('destination parent does not exist: ' + str(parent))
    for digest, name in checksums(here / 'metadata.sha256'):
        if checksum_file(here / name) != digest:
            raise ValueError('metadata checksum mismatch: ' + name)
    name = (here / 'folder-name.txt').read_text(encoding='ascii').strip()
    if name != 'SAT2024':
        raise ValueError('unexpected folder name')
    destination = parent / name
    if os.path.lexists(destination):
        raise ValueError('destination already exists: ' + str(destination))
    manifest = json.loads((here / 'manifest.json').read_text(encoding='ascii'))
    expected = {row['path']: row for row in manifest['files']}
    if len(expected) != len(manifest['files']):
        raise ValueError('duplicate manifest paths')
    part_rows = checksums(here / 'parts.sha256')
    actual_parts = sorted('parts/' + p.name for p in (here / 'parts').iterdir())
    if not part_rows or [p for _, p in part_rows] != actual_parts:
        raise ValueError('missing, unexpected, or unordered parts')
    archive_rows = checksums(here / 'archive.sha256')
    if len(archive_rows) != 1 or archive_rows[0][1] != name + '.tar.gz':
        raise ValueError('unexpected archive checksum manifest')
    # Both the decoded archive and restored files coexist during reconstruction.
    needed = manifest['archive_bytes'] + manifest['total_file_bytes'] + 64 * BLOCK
    if shutil.disk_usage(parent).free < needed:
        raise ValueError('insufficient free space; need approximately %d bytes' % needed)
    with tempfile.TemporaryDirectory(prefix='.' + name + '.reconstruct-', dir=parent) as temp:
        stage = Path(temp)
        archive = stage / (name + '.tar.gz')
        archive_hash = hashlib.sha256()
        carry = b''
        padded = False
        with archive.open('xb') as output:
            for index, (digest, relative) in enumerate(part_rows, 1):
                h = hashlib.sha256()
                with (here / relative).open('rb') as part:
                    for block in iter(lambda: part.read(BLOCK), b''):
                        h.update(block)
                        encoded = carry + b''.join(block.split())
                        end = len(encoded) // 4 * 4
                        ready, carry = encoded[:end], encoded[end:]
                        if ready:
                            if padded:
                                raise ValueError('Base64 data after padding')
                            decoded = base64.b64decode(ready, validate=True)
                            padded = b'=' in ready
                            output.write(decoded)
                            archive_hash.update(decoded)
                if h.hexdigest() != digest:
                    raise ValueError('part checksum mismatch: ' + relative)
                if index == 1 or index % 10 == 0 or index == len(part_rows):
                    print('verified and decoded parts: %d/%d' % (index, len(part_rows)), flush=True)
        if carry:
            raise ValueError('incomplete Base64 data')
        if archive.stat().st_size != manifest['archive_bytes'] or archive_hash.hexdigest() != archive_rows[0][0]:
            raise ValueError('archive checksum or size mismatch')
        restored = stage / name
        restored.mkdir()
        seen = set()
        root_seen = False
        with tarfile.open(archive, mode='r|gz') as bundle:
            for member in bundle:
                p = PurePosixPath(member.name)
                if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != name:
                    raise ValueError('unsafe archive path: ' + member.name)
                if member.isdir() and p == PurePosixPath(name) and not root_seen:
                    root_seen = True
                    continue
                relative = str(PurePosixPath(*p.parts[1:]))
                if not member.isfile() or relative not in expected or relative in seen:
                    raise ValueError('unexpected archive member: ' + member.name)
                row = expected[relative]
                if member.size != row['size']:
                    raise ValueError('file size mismatch: ' + relative)
                target = restored / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                h = hashlib.sha256()
                with bundle.extractfile(member) as source, target.open('xb') as output:
                    for block in iter(lambda: source.read(BLOCK), b''):
                        h.update(block)
                        output.write(block)
                if h.hexdigest() != row['sha256']:
                    raise ValueError('file checksum mismatch: ' + relative)
                target.chmod(row['mode'] & 0o777)
                os.utime(target, (row['mtime_ns'] / 1e9, row['mtime_ns'] / 1e9))
                seen.add(relative)
                if len(seen) % 50 == 0 or len(seen) == len(expected):
                    print('verified files: %d/%d' % (len(seen), len(expected)), flush=True)
        if not root_seen or seen != set(expected):
            raise ValueError('archive is missing expected entries')
        if os.path.lexists(destination):
            raise ValueError('destination appeared during reconstruction: ' + str(destination))
        # mkdir refuses an existing destination even if another process creates it.
        destination.mkdir()
        try:
            for item in restored.iterdir():
                shutil.move(str(item), str(destination / item.name))
            destination.chmod(manifest['root_mode'] & 0o777)
        except BaseException:
            # Retain a partial destination for inspection if publication fails.
            raise
    print('reconstructed and verified: %s (%d files; %d benchmark instances)' % (
        destination, len(expected), manifest['benchmark_instances']))


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('reconstruction failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
