#!/usr/bin/env python3
"""Configure native MCP while preserving every unrelated config field and byte."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib

NAME = 'harness2-local'
TOOLS = ('h2_context', 'h2_assess', 'h2_feedback', 'h2_start', 'h2_status',
         'h2_propose', 'h2_probe', 'h2_adopt', 'h2_reflect', 'h2_recall')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-bin', required=True)
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-tools', nargs='+', choices=TOOLS, default=[],
                        help='Explicitly trust only these reviewed local tools for noninteractive use; no default trust change')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    server = root / 'server/harness2_local.py'
    python = shutil.which('python3')
    if not python or not server.is_file():
        raise SystemExit('A working python3 and the bundled server are required')
    binary = str(Path(args.codex_bin).expanduser().resolve())
    config = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    if config.is_symlink():
        raise SystemExit('config.toml is a managed symlink; keep it intact and review its owner')
    raw = config.read_bytes() if config.exists() else b''
    before = tomllib.loads(raw.decode())
    desired = {'command': python, 'args': [str(server), '--stdio']}
    existing = before.get('mcp_servers', {}).get(NAME)
    if existing and (existing.get('type', 'stdio') != 'stdio'
                     or any(key in existing for key in ('url', 'server_url', 'bearer_token_env_var'))):
        raise SystemExit('The server name has conflicting transport settings; keep its policy intact')
    if existing and (existing.get('command') != python or existing.get('args') != desired['args']):
        raise SystemExit('The server name is already owned by a different command; keep it intact and resolve ownership')
    evidence = Path(args.evidence_dir).expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    requested_tools = sorted(set(args.approve_tools))
    existing_tools = (existing or {}).get('tools', {})
    for name in requested_tools:
        mode = existing_tools.get(name, {}).get('approval_mode')
        if mode not in (None, 'approve'):
            raise SystemExit('An explicit tool approval policy already exists; keep it intact and review ownership')
    missing_tools = [name for name in requested_tools if existing_tools.get(name, {}).get('approval_mode') != 'approve']
    for name in missing_tools:
        if name in existing_tools:
            raise SystemExit('An existing tool table must be reviewed before adding approval settings')
    report = {'server': NAME, 'desired': desired, 'codex_binary': binary,
              'explicitly_approved_tools': requested_tools,
              'transport': 'stdio', 'source': 'native-user-config', 'applied': False}
    (evidence / 'native-mcp.candidate.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.apply:
        if existing and existing.get('enabled', True) and not missing_tools:
            report.update(applied=True, already_current=True)
        else:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = config.parent / 'backups' / f'harness2-native-mcp-{stamp}' / 'config.toml.before'
            backup.parent.mkdir(parents=True, mode=0o700)
            backup.write_bytes(raw)
            backup.chmod(0o600)
            if (config.read_bytes() if config.exists() else b'') != raw:
                raise SystemExit('Configuration changed concurrently; keep the candidate without overwriting')
            if existing and not existing.get('enabled', True):
                raise SystemExit('Owned server is explicitly disabled; keep its policy intact and review before enabling')
            # Current desktop CLI mcp-add reserializes every MCP definition and drops
            # fields it does not recognize. The documented native config.toml route
            # permits an append confined to this server, preserving all prior bytes.
            suffix = '' if existing else ('\n\n[mcp_servers.' + json.dumps(NAME) + ']\n'
                      + 'command = ' + json.dumps(python) + '\n'
                      + 'args = ' + json.dumps(desired['args']) + '\n')
            for name in missing_tools:
                suffix += ('\n[mcp_servers.' + json.dumps(NAME) + '.tools.' + name + ']\n'
                           + 'approval_mode = "approve"\n')
            updated = raw + suffix.encode()
            after = tomllib.loads(updated.decode())
            actual = after.get('mcp_servers', {}).get(NAME, {})
            if actual.get('command') != python or actual.get('args') != desired['args'] or not actual.get('enabled', True):
                raise RuntimeError('Native MCP registration did not match the requested command')
            old_other = dict(before)
            new_other = dict(after)
            old_other['mcp_servers'] = dict(before.get('mcp_servers', {}))
            new_other['mcp_servers'] = dict(after.get('mcp_servers', {}))
            old_other['mcp_servers'].pop(NAME, None)
            new_other['mcp_servers'].pop(NAME, None)
            if not old_other['mcp_servers']:
                old_other.pop('mcp_servers')
            if not new_other['mcp_servers']:
                new_other.pop('mcp_servers')
            if old_other != new_other:
                raise RuntimeError('Unrelated config changed; preserve evidence and inspect instead of claiming success')
            if (config.read_bytes() if config.exists() else b'') != raw:
                raise RuntimeError('Configuration changed concurrently; do not overwrite')
            fd, temporary = tempfile.mkstemp(prefix='.h2-native-mcp-', dir=config.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, config.stat().st_mode & 0o777 if config.exists() else 0o600)
                if config.is_symlink() or (config.read_bytes() if config.exists() else b'') != raw:
                    raise RuntimeError('Configuration changed while preparing the atomic update; do not overwrite')
                os.replace(temporary, config)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            if config.read_bytes() != updated:
                raise RuntimeError('Native config readback mismatch')
            report.update(applied=True, backup=str(backup), unrelated_config_preserved=True,
                          original_bytes_preserved=updated.startswith(raw),
                          config_sha256=hashlib.sha256(config.read_bytes()).hexdigest())
    (evidence / 'native-mcp-install.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
