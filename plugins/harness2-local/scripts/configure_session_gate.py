#!/usr/bin/env python3
"""Opt in to a reviewed Harness2 developer instruction without replacing other config."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import tomllib

BEGIN = '# BEGIN HARNESS2_DEVELOPER_GATE v1'
END = '# END HARNESS2_DEVELOPER_GATE'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    guide = (root / 'references/developer-kickoff.md').read_text().strip()
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser()
    if not home.is_absolute():
        raise SystemExit('CODEX_HOME must be absolute')
    target = home / 'config.toml'
    if target.is_symlink():
        raise SystemExit('config.toml is a managed symlink; keep its owner intact')
    raw = target.read_bytes() if target.exists() else b''
    text = raw.decode()
    before = tomllib.loads(text)
    remainder = raw
    if BEGIN in text or END in text:
        if not text.startswith(BEGIN + '\n') or text.count(BEGIN) != 1 or text.count(END) != 1:
            raise SystemExit('Ambiguous developer gate markers; do not overwrite')
        owned, suffix = text.split(END + '\n', 1)
        parsed_owned = tomllib.loads(owned.split('\n', 1)[1])
        if set(parsed_owned) != {'developer_instructions'}:
            raise SystemExit('Owned block has other settings; preserve and inspect')
        remainder = suffix.encode()
        if 'developer_instructions' in tomllib.loads(suffix):
            raise SystemExit('Developer instructions exist outside the owned gate')
    elif 'developer_instructions' in before:
        raise SystemExit('Existing developer_instructions have another owner; keep them intact and review integration')
    prefix = BEGIN + '\n' + 'developer_instructions = ' + json.dumps(guide, ensure_ascii=False) + '\n' + END + '\n'
    updated = prefix.encode() + remainder
    after = tomllib.loads(updated.decode())
    previous_other = {k: v for k, v in before.items() if k != 'developer_instructions'}
    next_other = {k: v for k, v in after.items() if k != 'developer_instructions'}
    if previous_other != next_other or after['developer_instructions'] != guide:
        raise RuntimeError('Unrelated configuration must remain identical')
    evidence = Path(args.evidence_dir).expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    candidate = evidence / 'developer-gate.candidate.md'
    candidate.write_text(guide + '\n')
    candidate.chmod(0o600)
    report = {'target': str(target), 'candidate': str(candidate), 'applied': False,
              'guide_sha256': hashlib.sha256(guide.encode()).hexdigest(),
              'before_sha256': hashlib.sha256(raw).hexdigest(),
              'after_sha256': hashlib.sha256(updated).hexdigest(),
              'unrelated_config_preserved': True}
    if args.apply and updated != raw:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = home / 'backups' / f'harness2-session-gate-{stamp}' / 'config.toml.before'
        backup.parent.mkdir(parents=True, mode=0o700)
        backup.write_bytes(raw)
        backup.chmod(0o600)
        fd, name = tempfile.mkstemp(prefix='.h2-session-gate-', dir=home)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, target.stat().st_mode & 0o777 if target.exists() else 0o600)
            if target.is_symlink() or (target.read_bytes() if target.exists() else b'') != raw:
                raise RuntimeError('Config changed concurrently; keep candidate without overwriting')
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        if target.read_bytes() != updated:
            raise RuntimeError('Config readback mismatch')
        report.update(applied=True, backup=str(backup), config_sha256=hashlib.sha256(updated).hexdigest())
    elif args.apply:
        report.update(applied=True, already_current=True, config_sha256=hashlib.sha256(raw).hexdigest())
    output = evidence / 'session-gate-install.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
