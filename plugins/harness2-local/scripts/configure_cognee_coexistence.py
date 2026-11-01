#!/usr/bin/env python3
"""Install the optional external Enola snapshot adapter; never restart Cognee."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PTH = 'harness2_cognee_external.pth'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Managed paths must not be symlinks')
    return path


def atomic(path, data, before):
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix='.h2-cognee-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        safe(path)
        require((path.read_bytes() if path.exists() else None) == before, 'Concurrent change; refusing overwrite')
        os.replace(temporary, path)
        require(path.read_bytes() == data, 'Installed file readback mismatch')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv', required=True, help='Existing Cognee venv; no package install or upgrade')
    parser.add_argument('--cache-root', required=True, help='Private cache outside indexed business projects')
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    venv = Path(args.venv).expanduser().absolute()
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    require((venv / 'pyvenv.cfg').is_file() and python.is_file(), 'An existing Cognee venv is required')
    # Query metadata without importing Cognee or reading any account configuration.
    code = ('import sysconfig,json; from importlib.metadata import version; '
            'print(json.dumps({"purelib":sysconfig.get_path("purelib"),'
            '"cognee":version("cognee"),"enola_cli":version("enola-cli")}))')
    result = subprocess.run([str(python), '-c', code], capture_output=True, text=True,
                            timeout=20, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    require(result.returncode == 0, 'Cannot query the existing Cognee runtime metadata')
    metadata = json.loads(result.stdout)
    purelib = safe(Path(metadata['purelib']))
    require(purelib.is_relative_to(venv.resolve()), 'Interpreter does not belong to the selected venv')
    enola = purelib / 'cognee/tasks/code_graph/enola.py'
    source = Path(__file__).resolve().parents[1] / 'integrations/cognee_external.py'
    require(enola.is_file() and source.is_file(), 'Required adapter or Cognee Enola source is missing')
    cache = safe(Path(args.cache_root).expanduser().absolute())
    home = safe(Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().absolute())
    config = {'cache_root': str(cache), 'expected_enola_sha256': sha(enola.read_bytes())}
    files = {'cognee_external.py': source.read_bytes(),
             'config.json': (json.dumps(config, sort_keys=True, indent=2) + '\n').encode()}
    bundle = sha(json.dumps({k: sha(v) for k, v in files.items()}, sort_keys=True).encode())
    runtime = safe(home / 'harness2-local/cognee-runtime' / bundle)
    pth = safe(purelib / PTH)
    old = pth.read_bytes() if pth.exists() else None
    require(not pth.is_symlink(), 'Existing .pth is a symlink; review its owner')
    if old is not None:
        lines = old.decode().splitlines()
        require(len(lines) == 2 and lines[1] == 'import cognee_external; cognee_external.install()'
                and Path(lines[0]).parent == home / 'harness2-local/cognee-runtime',
                'Existing .pth has a different owner; refusing overwrite')
    data = (str(runtime) + '\nimport cognee_external; cognee_external.install()\n').encode()
    report = {'applied': False, 'runtime': str(runtime), 'pth': str(pth), 'cache_root': str(cache),
              'metadata': metadata, 'enola_module_sha256': config['expected_enola_sha256'],
              'restart_performed': False, 'activation': 'next Cognee server process start',
              'business_files_modified': False, 'original_cognee_package_modified': False}
    evidence = Path(args.evidence_dir).expanduser().absolute()
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.apply:
        if runtime.exists():
            require({p.name for p in runtime.iterdir()} == set(files)
                    and all(safe(runtime / k).is_file() and (runtime / k).read_bytes() == v
                            for k, v in files.items()),
                    'Existing immutable runtime changed; preserve it for diagnosis')
        else:
            runtime.mkdir(parents=True, mode=0o700)
            for name, content in files.items():
                atomic(runtime / name, content, None)
                (runtime / name).chmod(0o400)
            runtime.chmod(0o500)
        if old != data:
            if old is not None:
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup = home / 'backups' / ('harness2-cognee-' + stamp) / PTH
                atomic(backup, old, None)
                report['backup'] = str(backup)
            atomic(pth, data, old)
        report.update(applied=True, already_current=old == data, pth_sha256=sha(data))
    output = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    target = evidence / 'cognee-coexistence-install.json'
    atomic(target, output, target.read_bytes() if target.exists() else None)
    print(output.decode(), end='')


if __name__ == '__main__':
    main()
