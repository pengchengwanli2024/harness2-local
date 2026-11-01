"""Optional Cognee adapter tests: real files/imports; no Cognee/API installation."""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ADAPTER = Path(__file__).resolve().parents[1] / "plugins/harness2-local/integrations/cognee_external.py"
SPEC = importlib.util.spec_from_file_location("cognee_external_tested", ADAPTER)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def tree_state(root):
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_mtime_ns, stat.S_IMODE(info.st_mode),
            os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None)
    return result


def remove_readonly(root):
    for folder, dirs, files in os.walk(root):
        os.chmod(folder, 0o700)
        for name in files:
            path = Path(folder) / name
            if not path.is_symlink():
                path.chmod(0o600)
    shutil.rmtree(root)


class ExternalAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cognee-external-test-")).resolve()
        self.addCleanup(remove_readonly, self.root)
        self.cache = self.root / "cache"
        self.origin = self.root / "upstream_enola.py"
        self.origin.write_text("# pinned upstream source\n")
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"cache_root": str(self.cache),
            "expected_enola_sha256": adapter._hash(self.origin.read_bytes())}))
        self.config_patch = mock.patch.object(adapter, "CONFIG_PATH", self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.repo = self.root / "work" / "same-name"
        self.repo.mkdir(parents=True)
        (self.repo / "service.py").write_text("def compute():\n    return 42\n")
        (self.repo / ".enola").mkdir()
        (self.repo / ".enola/facts.jsonl").write_text("OLD BUSINESS SNAPSHOT\n")
        self.calls = []

    async def original(self, repo_path, timeout=600.0):
        mirror = Path(repo_path)
        self.calls.append((mirror, timeout))
        self.assertNotEqual(mirror, self.repo)
        self.assertEqual(mirror.name, self.repo.name)
        self.assertFalse((mirror / ".enola/facts.jsonl").exists())
        self.assertFalse((mirror / "service.py").stat().st_mode & 0o222)
        self.assertFalse(mirror.stat().st_mode & 0o222)
        (mirror / ".enola/facts.jsonl").write_text(json.dumps({
            "repo": mirror.name, "kind": "function", "name": "compute", "file": "service.py"
        }) + "\n")
        (mirror / ".enola/insights.json").write_text("[]")
        (mirror / ".enola/flows.json").write_text('{"flows": []}')
        return mirror / ".enola"

    async def generate(self, repo=None, original=None):
        return await adapter._generate(original or self.original, self.origin,
                                       repo or self.repo, timeout=13.0)

    async def test_source_and_old_enola_bytes_modes_mtimes_unchanged(self):
        for name in (".git", "node_modules", ".harness2", "dist", "__pycache__"):
            (self.repo / name).mkdir()
            (self.repo / name / "ignore.py").write_text("excluded")
        for name in (".env", ".env.production", "auth.json", "secret.key", "private.pem"):
            (self.repo / name).write_text("EXCLUDED FIXTURE SECRET")
        outside = self.root / "outside.py"
        outside.write_text("not source")
        (self.repo / "external-link.py").symlink_to(outside)
        (self.repo / "directory-link").symlink_to(outside.parent, target_is_directory=True)
        before = tree_state(self.repo)
        result = await self.generate()
        self.assertEqual(tree_state(self.repo), before)
        self.assertTrue(result.is_relative_to(self.cache))
        self.assertEqual(self.calls[0][1], 13.0)
        mirror = result.parent
        self.assertEqual(sorted(p.name for p in mirror.iterdir()), [".enola", "service.py"])
        self.assertNotEqual((self.repo / "service.py").stat().st_ino,
                            (mirror / "service.py").stat().st_ino)
        manifest = json.loads((mirror.parent / "manifest.json").read_text())
        self.assertEqual(manifest["source_path"], str(self.repo.resolve()))
        self.assertEqual(manifest["source_key"], adapter._hash(os.fsencode(str(self.repo))))
        self.assertEqual(manifest["files"]["service.py"]["sha256"],
                         adapter._hash((self.repo / "service.py").read_bytes()))
        self.assertEqual(manifest["manifest_sha256"],
                         adapter._hash(json.dumps(manifest["files"], sort_keys=True).encode()))
        self.assertFalse(result.stat().st_mode & 0o222)
        self.assertFalse((result / "facts.jsonl").stat().st_mode & 0o222)

    async def test_same_basename_projects_and_old_generations_are_isolated(self):
        first = await self.generate()
        old = tree_state(first.parent.parent)
        (self.repo / "service.py").write_text("def compute():\n    return 43\n")
        second = await self.generate()
        self.assertNotEqual(first, second)
        self.assertEqual(tree_state(first.parent.parent), old)
        other = self.root / "other" / self.repo.name
        other.mkdir(parents=True)
        (other / "service.py").write_text("def compute(): return 99\n")
        third = await self.generate(other)
        self.assertEqual(third.parent.name, first.parent.name)
        self.assertNotEqual(third.parents[2], first.parents[2])
        self.assertEqual(tree_state(first.parent.parent), old)

    async def test_generation_failure_preserved_no_source_fallback_or_old_mapping(self):
        await self.generate()
        before = tree_state(self.repo)

        async def broken(mirror, timeout=600.0):
            self.calls.append((Path(mirror), timeout))
            (Path(mirror) / ".enola/partial.json").write_text("partial")
            raise RuntimeError("fixture extraction failed")

        with self.assertRaises(RuntimeError):
            await self.generate(original=broken)
        self.assertEqual(tree_state(self.repo), before)
        self.assertTrue(all(path.is_relative_to(self.cache) for path, _ in self.calls))
        with self.assertRaises(adapter.ExternalIndexError):
            adapter._resolve_snapshot(self.repo / ".enola")
        results = [json.loads(p.read_text())["status"] for p in self.cache.rglob("result.json")]
        self.assertCountEqual(results, ["passed", "failed"])
        self.assertTrue(list(self.cache.rglob("partial.json")))

    async def test_hash_mismatch_prevents_index_before_source_or_cache_work(self):
        self.origin.write_text("# upgraded upstream\n")
        with self.assertRaises(adapter.ExternalIndexError):
            await self.generate()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.cache.exists())

    async def test_explicit_unexpected_output_rejected(self):
        async def wrong_path(mirror, timeout=600.0):
            return self.repo / ".enola"
        with self.assertRaises(adapter.ExternalIndexError):
            await self.generate(original=wrong_path)
        with self.assertRaises(adapter.ExternalIndexError):
            adapter._resolve_snapshot(self.repo / ".enola")

    async def test_reader_mapping_preserves_source_identity_and_is_context_local(self):
        snapshot = await self.generate()
        self.assertEqual(adapter._resolve_snapshot(self.repo / ".enola"), snapshot)
        self.assertEqual(adapter._resolve_snapshot(snapshot), snapshot)
        # A fresh task/context must never read the old real-tree snapshot as fallback.
        async def isolated():
            adapter._SNAPSHOTS.set(None)
            with self.assertRaises(adapter.ExternalIndexError):
                adapter._resolve_snapshot(self.repo / ".enola")
        await asyncio.create_task(isolated())
        self.assertEqual(adapter._resolve_snapshot(self.repo / ".enola"), snapshot)

    async def test_concurrent_indexes_bind_each_call_to_its_own_generation(self):
        async def index():
            snapshot = await self.generate()
            await asyncio.sleep(0.02)
            self.assertEqual(adapter._resolve_snapshot(self.repo / ".enola"), snapshot)
            return snapshot
        first, second = await asyncio.gather(index(), index())
        self.assertNotEqual(first, second)

    async def test_no_yaml_dependency_needed_without_source_config(self):
        with mock.patch.dict(sys.modules, {"yaml": None}):
            self.assertTrue((await self.generate()).is_dir())
        (self.repo / "mcp-arch.yaml").write_text("extractors: [python]\n")
        with mock.patch.dict(sys.modules, {"yaml": None}), self.assertRaises(adapter.ExternalIndexError):
            await self.generate()

    async def test_config_kept_verbatim_and_unsafe_modes_fail_closed(self):
        # Test parser policy with a tiny stand-in; real PyYAML availability is optional.
        source_config = "extractors: [python]\nignore: ['generated/**']\n"
        (self.repo / "mcp-arch.yaml").write_text(source_config)
        parsed = {"extractors": ["python"], "ignore": ["generated/**"]}
        fake_yaml = mock.Mock()
        fake_yaml.safe_load.return_value = parsed
        with mock.patch.dict(sys.modules, {"yaml": fake_yaml}):
            snapshot = await self.generate()
            self.assertEqual((snapshot.parent / "mcp-arch.yaml").read_text(), source_config)
            for config in ({"repos": []}, {"repo": ".."}, {"output": {"dir": str(self.repo)}},
                           {"providers": [{"command": ["anything"]}]},
                           {"history": {"dir": str(self.repo)}}, ["invalid"]):
                with self.subTest(config=config):
                    fake_yaml.safe_load.return_value = config
                    with self.assertRaises(adapter.ExternalIndexError):
                        await self.generate()


FAKE_ENOLA = '''from pathlib import Path
memory_sentinel = "MEMORY_AVAILABLE"
async def run_enola_generate(repo_path, timeout=600.0):
    root = Path(repo_path)
    (root / ".enola/facts.jsonl").write_text('{"repo": "' + root.name + '", "kind": "function"}\\n')
    (root / ".enola/insights.json").write_text("[]")
    (root / ".enola/flows.json").write_text("[]")
    return root / ".enola"
def parse_enola_snapshot(snapshot_dir):
    return {name: (Path(snapshot_dir) / name).read_text() for name in
            ("facts.jsonl", "insights.json", "flows.json")}
def snapshot_identity(snapshot_dir, receipt):
    return (Path(snapshot_dir) / "facts.jsonl").read_text()
'''


class LoaderTests(unittest.TestCase):
    def test_real_pathfinder_import_from_callers_memory_and_stale_pin(self):
        with tempfile.TemporaryDirectory(prefix="cognee-import-test-") as folder:
            root = Path(folder).resolve()
            runtime = root / "runtime"
            runtime.mkdir()
            shutil.copyfile(ADAPTER, runtime / "cognee_external.py")
            package = root / "packages"
            target = package / "cognee/tasks/code_graph"
            target.mkdir(parents=True)
            for directory in (package / "cognee", package / "cognee/tasks", target):
                (directory / "__init__.py").write_text("")
            source = target / "enola.py"
            source.write_text(FAKE_ENOLA)
            distribution = package / "cognee_external_loader_fixture-1.0.dist-info"
            distribution.mkdir()
            (distribution / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: cognee-external-loader-fixture\nVersion: 1.0\n")
            (target / "caller.py").write_text('''from .enola import run_enola_generate, parse_enola_snapshot, snapshot_identity
async def pipeline(repo_path, data_identity):
    snapshot = await run_enola_generate(repo_path)
    nodes = parse_enola_snapshot(snapshot)
    # Cognee add_code_graph_edges reconstructs source/.enola after await nodes load.
    edges = parse_enola_snapshot(repo_path / ".enola")
    identity = snapshot_identity(repo_path / ".enola", None)
    return repo_path, data_identity, snapshot, nodes, edges, identity
''')
            repo = root / "business"
            repo.mkdir()
            (repo / "service.py").write_text("def f(): return 1\n")
            (repo / ".enola").mkdir()
            (repo / ".enola/facts.jsonl").write_text("OLD SOURCE FACTS")
            (runtime / "config.json").write_text(json.dumps({
                "cache_root": str(root / "cache"),
                "expected_enola_sha256": adapter._hash(source.read_bytes())}))
            script = '''import asyncio, importlib, importlib.machinery, json, sys
from pathlib import Path
import cognee_external
before = list(sys.meta_path)
cognee_external.install()
cognee_external.install()
assert sum(bool(getattr(x, "__cognee_external__", False)) for x in sys.meta_path) == 1
assert len(sys.meta_path) == len(before)
from importlib.metadata import version
assert version("cognee-external-loader-fixture") == "1.0"
from cognee.tasks.code_graph import enola, caller
assert enola.memory_sentinel == "MEMORY_AVAILABLE"
assert hasattr(enola.__loader__, "get_source")
assert enola.__loader__.get_source(enola.__name__)
repo = Path(sys.argv[1])
async def main():
    marker = object()
    result = await caller.pipeline(repo, marker)
    assert result[0] == repo and result[1] is marker
    assert result[2].is_relative_to(Path(sys.argv[2]))
    assert result[3] == result[4]
    assert result[5] != "OLD SOURCE FACTS"
    assert (repo / ".enola/facts.jsonl").read_text() == "OLD SOURCE FACTS"
asyncio.run(main())
# Reload still imports ordinary memory after an incompatible source upgrade.
source = Path(enola.__file__)
source.write_text(source.read_text() + "\\n# new upstream version\\n")
importlib.reload(enola)
assert enola.memory_sentinel == "MEMORY_AVAILABLE"
try:
    asyncio.run(enola.run_enola_generate(repo))
except cognee_external.ExternalIndexError:
    pass
else:
    raise AssertionError("stale source pin was not rejected")
print("IMPORT_AND_CALLER_PIPELINE_OK")
'''
            result = subprocess.run([sys.executable, "-B", "-c", script, str(repo), str(root / "cache")],
                                    env={**os.environ, "PYTHONPATH": os.pathsep.join([str(runtime), str(package)])},
                                    capture_output=True, text=True, timeout=30)
            # Subprocess sealed generations must be made removable before TemporaryDirectory cleanup.
            if (root / "cache").exists():
                for directory, _, files in os.walk(root / "cache"):
                    os.chmod(directory, 0o700)
                    for name in files:
                        (Path(directory) / name).chmod(0o600)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("IMPORT_AND_CALLER_PIPELINE_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
