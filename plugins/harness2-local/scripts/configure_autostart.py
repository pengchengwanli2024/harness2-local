#!/usr/bin/env python3
"""Append/update the explicitly authorized kickoff policy without changing other rules."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile

BEGIN = '<!-- BEGIN HARNESS2_AUTO_KICKOFF v1 -->'
END = '<!-- END HARNESS2_AUTO_KICKOFF -->'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--evidence-dir', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).resolve()
    target = home / 'AGENTS.md'
    if (home / 'AGENTS.override.md').exists() and (home / 'AGENTS.override.md').stat().st_size:
        raise SystemExit('A global AGENTS.override.md shadows AGENTS.md; inspect that explicit override before changing policy.')
    if target.is_symlink():
        raise SystemExit('Global AGENTS.md is a symlink; inspect ownership before replacing.')
    original = target.read_bytes() if target.exists() else b''
    old = original.decode()
    block = (root / 'references/global-kickoff.md').read_text().replace('{{PLUGIN_ROOT}}', str(root)).strip()
    if BEGIN in old:
        if old.count(BEGIN) != 1 or old.count(END) != 1:
            raise SystemExit('Ambiguous kickoff markers; do not overwrite existing guidance.')
        left, rest = old.split(BEGIN, 1)
        _, right = rest.split(END, 1)
        updated = left + block + right
    else:
        if END in old:
            raise SystemExit('Incomplete existing policy markers')
        updated = old + ('\n\n' if old else '') + block + '\n'
    data = updated.encode()
    if len(data) > 30000:
        raise SystemExit('Combined global guidance approaches the default size budget; review before applying.')
    evidence = Path(args.evidence_dir).expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'global-AGENTS.candidate.md').write_bytes(data)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = {'target': str(target), 'candidate': str(evidence / 'global-AGENTS.candidate.md'),
              'before_sha256': sha(original), 'after_sha256': sha(data), 'bytes': len(data),
              'unchanged_existing_prefix': BEGIN not in old and data.startswith(original),
              'applied': False}
    if args.apply and original != data:
        backup = home / 'backups' / f'harness2-autostart-{stamp}' / 'AGENTS.md.before'
        backup.parent.mkdir(parents=True, mode=0o700)
        backup.write_bytes(original)
        backup.chmod(0o600)
        fd, name = tempfile.mkstemp(prefix='.h2-agents-', dir=home)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, target.stat().st_mode & 0o777 if target.exists() else 0o600)
            # Guard against another task editing global rules after this candidate was built.
            if (target.read_bytes() if target.exists() else b'') != original:
                raise RuntimeError('Global guidance changed concurrently; retain candidate for review')
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        if target.read_bytes() != data:
            raise RuntimeError('Global guidance readback mismatch')
        report.update(applied=True, backup=str(backup))
    elif args.apply:
        report.update(applied=True, already_current=True)
    (evidence / 'global-policy-install.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
