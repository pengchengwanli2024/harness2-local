"""Optional, version-pinned Cognee Enola storage adapter (stdlib at startup).

A .pth file adds this immutable runtime directory and calls install(). Only
the normal PathFinder's loader for TARGET is wrapped. Import/memory operations
remain available if configuration or the Enola source pin is stale; indexing
then fails closed. No user source tree or previous generation is written.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import fcntl
import functools
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

TARGET = "cognee.tasks.code_graph.enola"
CONFIG_PATH = Path(__file__).with_name("config.json")
EXCLUDED_DIRS = frozenset({
    ".git", ".enola", ".harness2", ".harness2-preflight", ".codex", ".claude",
    "node_modules", "vendor", ".venv", "venv", "site-packages", "__pycache__",
    ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "build", "dist", "target", "coverage", ".next", ".nuxt", ".turbo",
    ".gradle", "Pods", ".idea", ".DS_Store", ".svn", ".hg", ".aws", ".ssh",
})
SECRET_NAMES = frozenset({
    ".env", "auth.json", "credentials.json", "credentials", "secrets.json",
    "secrets.yaml", "secrets.yml", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".npmrc", ".pypirc", ".netrc", "service-account.json", "service_account.json",
})
CONFIG_NAMES = frozenset({"mcp-arch.yaml", "mcp-arch.yml"})
_SNAPSHOTS = contextvars.ContextVar("cognee_external_snapshots", default=None)


class ExternalIndexError(RuntimeError):
    """An optional index adapter cannot safely run; ordinary memory is unaffected."""


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _json(path, value):
    # All destinations are inside a newly allocated, externally locked generation.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _settings():
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        root = Path(raw["cache_root"]).expanduser()
        pin = raw["expected_enola_sha256"]
        if not root.is_absolute() or not isinstance(pin, str) or len(pin) != 64:
            raise ValueError("invalid cache root or pin")
        int(pin, 16)
        return root.resolve(), pin.lower()
    except Exception as exc:
        raise ExternalIndexError("Cognee external index configuration is invalid; reinstall adapter") from exc


def _excluded(name):
    lower = name.lower()
    return (name in EXCLUDED_DIRS or lower in SECRET_NAMES or lower.startswith(".env.")
            or lower.endswith((".pem", ".key", ".p12", ".pfx", ".keystore")))


def _config_policy(data):
    """Keep safe source config bytes; do not silently rewrite extraction settings."""
    try:
        import yaml  # Optional and lazy: absent YAML does not break memory imports.
    except ImportError as exc:
        raise ExternalIndexError("PyYAML is required to validate repository Enola configuration") from exc
    try:
        document = yaml.safe_load(data)
    except Exception as exc:
        raise ExternalIndexError("Cannot safely parse repository Enola configuration") from exc
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ExternalIndexError("Enola configuration must be a mapping")
    if "repos" in document:
        raise ExternalIndexError("Cluster repos configuration is not supported by external indexing")
    if document.get("repo") not in (None, "", "."):
        raise ExternalIndexError("Enola repo overrides are not supported by external indexing")
    output = document.get("output") or {}
    history = document.get("history") or {}
    if not isinstance(output, dict) or output.get("dir") not in (None, "", ".enola"):
        raise ExternalIndexError("Custom Enola output directories are not supported")
    if (not isinstance(history, dict) or history.get("dir") or history.get("shared_dir")
            or document.get("providers")):
        raise ExternalIndexError("External history paths and executable providers are not supported")


def _copy_tree(source, mirror):
    """Copy regular files via directory FDs; never follow even in-tree symlinks."""
    files, excluded = {}, []
    flags = os.O_RDONLY | os.O_NOFOLLOW

    def visit(fd, target, prefix=""):
        with os.scandir(fd) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                name = entry.name
                relative = f"{prefix}/{name}" if prefix else name
                info = entry.stat(follow_symlinks=False)
                if _excluded(name):
                    excluded.append(relative)
                    continue
                if stat.S_ISLNK(info.st_mode):
                    if not prefix and name in CONFIG_NAMES:
                        raise ExternalIndexError("Symlink Enola configuration is not supported")
                    excluded.append(relative)
                    continue
                dest = target / name
                if stat.S_ISDIR(info.st_mode):
                    nested = os.open(name, flags | os.O_DIRECTORY, dir_fd=fd)
                    try:
                        dest.mkdir()
                        visit(nested, dest, relative)
                    finally:
                        os.close(nested)
                elif stat.S_ISREG(info.st_mode):
                    origin = os.open(name, flags, dir_fd=fd)
                    try:
                        before = os.fstat(origin)
                        if not stat.S_ISREG(before.st_mode):
                            raise ExternalIndexError("Source changed while staging")
                        hasher = hashlib.sha256()
                        with os.fdopen(origin, "rb", closefd=False) as reader, dest.open("xb") as writer:
                            while chunk := reader.read(1024 * 1024):
                                writer.write(chunk)
                                hasher.update(chunk)
                        after = os.fstat(origin)
                        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                                after.st_size, after.st_mtime_ns, after.st_ino):
                            raise ExternalIndexError("Source changed while staging")
                        if not prefix and name in CONFIG_NAMES:
                            _config_policy(dest.read_bytes())
                        dest.chmod(0o444 | (before.st_mode & 0o111))
                        files[relative] = {"sha256": hasher.hexdigest(), "size": after.st_size}
                    finally:
                        os.close(origin)
                else:
                    excluded.append(relative)

    descriptor = os.open(source, flags | os.O_DIRECTORY)
    try:
        visit(descriptor, mirror)
    finally:
        os.close(descriptor)
    return files, excluded


def _seal(root):
    for folder, dirs, files in os.walk(root, topdown=False, followlinks=False):
        for name in files:
            path = Path(folder) / name
            if not path.is_symlink():
                path.chmod(0o444 | (path.stat().st_mode & 0o111))
        for name in dirs:
            path = Path(folder) / name
            if not path.is_symlink():
                path.chmod(0o555)
    root.chmod(0o555)


def _safe_cache_dir(path):
    # Reject redirecting existing cache components through symlinks.
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ExternalIndexError("Symlink external cache directories are not supported")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


@contextlib.asynccontextmanager
async def _project_lock(namespace, timeout):
    path = namespace / "index.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    acquired = False
    started = time.monotonic()
    try:
        while not acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                if time.monotonic() - started > timeout:
                    raise ExternalIndexError("Timed out waiting for external project index lock")
                await asyncio.sleep(0.05)
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _source_key(source):
    return str(source / ".enola")


async def _generate(original, module_origin, repo_path, timeout=600.0):
    cache, expected = _settings()
    # Verify before any mirror/source work; an upgrade blocks indexing, not imports.
    try:
        matches = _hash(Path(module_origin).read_bytes()) == expected
    except OSError:
        matches = False
    if not matches:
        raise ExternalIndexError("Pinned Cognee enola.py changed; reinstall external adapter before indexing")
    source = Path(repo_path).expanduser().resolve(strict=True)
    if not source.is_dir() or source == Path(source.anchor):
        raise ExternalIndexError("Index source must be a repository directory, not a filesystem root")
    if cache.is_relative_to(source) or source.is_relative_to(cache):
        raise ExternalIndexError("External cache and source tree must not overlap")
    mappings = dict(_SNAPSHOTS.get() or {})
    mappings.pop(_source_key(source), None)
    _SNAPSHOTS.set(mappings)
    namespace = cache / "projects" / _hash(os.fsencode(str(source)))
    _safe_cache_dir(namespace)
    async with _project_lock(namespace, timeout):
        generation = namespace / (time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex)
        generation.mkdir(mode=0o700)
        mirror = generation / source.name
        mirror.mkdir()
        manifest = {"source_path": str(source), "source_key": namespace.name,
                    "generation": generation.name, "expected_enola_sha256": expected}
        try:
            files, excluded = _copy_tree(source, mirror)
            manifest.update(files=files, excluded=excluded)
            manifest["manifest_sha256"] = _hash(json.dumps(files, sort_keys=True).encode())
            _json(generation / "manifest.json", manifest)
            # The sole writable location under this read-only source mirror.
            (mirror / ".enola").mkdir()
            for folder, _, _ in os.walk(mirror, topdown=False):
                if Path(folder) != mirror / ".enola":
                    Path(folder).chmod(0o555)
            snapshot = Path(await original(mirror, timeout=timeout))
            if snapshot.is_symlink() or snapshot.resolve() != (mirror / ".enola").resolve():
                raise ExternalIndexError("Enola returned an unexpected snapshot directory")
            if not (snapshot / "facts.jsonl").is_file() or (snapshot / "facts.jsonl").is_symlink():
                raise ExternalIndexError("External Enola snapshot has no regular facts.jsonl")
            _json(generation / "result.json", {"status": "passed", "snapshot_path": str(snapshot),
                                               "manifest_sha256": manifest["manifest_sha256"]})
        except BaseException as exc:
            if not (generation / "result.json").exists():
                _json(generation / "result.json", {"status": "failed", "error_type": type(exc).__name__,
                                                   "source_path": str(source)})
            raise
        finally:
            _seal(generation)
    mappings = dict(_SNAPSHOTS.get() or {})
    mappings[_source_key(source)] = str(snapshot)
    _SNAPSHOTS.set(mappings)
    return snapshot


def _resolve_snapshot(snapshot_dir):
    path = Path(snapshot_dir).expanduser()
    # Do not resolve .enola itself: it may be an original-tree symlink or stale cache.
    key = str(path.parent.resolve() / path.name)
    found = (_SNAPSHOTS.get() or {}).get(key)
    if found:
        return Path(found)
    cache, _ = _settings()
    if path.resolve().is_relative_to(cache):
        return path
    if path.name == ".enola":
        raise ExternalIndexError("No external snapshot bound to this async context; run external generation first")
    # Explicit snapshot artifacts elsewhere keep the upstream reader's normal semantics.
    return path


def _patch(module, origin):
    if getattr(module.run_enola_generate, "__cognee_external__", False):
        return
    original = module.run_enola_generate

    @functools.wraps(original)
    async def generate(repo_path, timeout=600.0):
        return await _generate(original, origin, repo_path, timeout)

    generate.__cognee_external__ = True
    module.run_enola_generate = generate
    for name in ("parse_enola_snapshot", "snapshot_identity"):
        reader = getattr(module, name, None)
        if reader is not None:
            def wrap(fn):
                @functools.wraps(fn)
                def read(snapshot_dir, *args, **kwargs):
                    return fn(_resolve_snapshot(snapshot_dir), *args, **kwargs)
                return read
            setattr(module, name, wrap(reader))


class _Loader:
    def __init__(self, original, origin):
        self.original, self.origin = original, origin

    def create_module(self, spec):
        creator = getattr(self.original, "create_module", None)
        return creator(spec) if creator else None

    def exec_module(self, module):
        self.original.exec_module(module)
        _patch(module, self.origin)

    def __getattr__(self, name):
        return getattr(self.original, name)


class _PathFinder:
    __cognee_external__ = True

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if fullname == TARGET and spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader, spec.origin)
        return spec

    def invalidate_caches(self):
        importlib.machinery.PathFinder.invalidate_caches()

    def find_distributions(self, *args, **kwargs):
        # importlib.metadata discovers installed distributions through this hook;
        # preserving module loading alone would break ordinary Cognee imports.
        return importlib.machinery.PathFinder.find_distributions(*args, **kwargs)


def install():
    """Idempotently wrap the standard finder; no config, model, or Cognee import."""
    if not any(getattr(finder, "__cognee_external__", False) for finder in sys.meta_path):
        for index, finder in enumerate(sys.meta_path):
            if finder is importlib.machinery.PathFinder:
                sys.meta_path[index] = _PathFinder()
                break
    module = sys.modules.get(TARGET)
    if module is not None:
        _patch(module, getattr(module, "__file__", ""))
