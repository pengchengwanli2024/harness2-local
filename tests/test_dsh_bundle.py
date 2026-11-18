"""DeepSeek Harness bundle contract: manifest, patch, display metadata and skill provider."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "harness2-local"
NODE = shutil.which("node")


def node_major():
    if NODE is None:
        return 0
    out = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout
    match = re.match(r"v(\d+)", out)
    return int(match.group(1)) if match else 0


def run_node(script):
    done = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=PLUGIN,
                          capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((PLUGIN / "package.json").read_text())

    def test_versions_agree_across_hosts(self):
        codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())["version"]
        generic = json.loads((PLUGIN / "plugin.json").read_text())["version"]
        self.assertEqual({self.manifest["version"]}, {codex, generic})

    def test_exports_and_files_exist(self):
        for key, target in self.manifest["exports"].items():
            if "*" in target:
                self.assertTrue(list(PLUGIN.glob(target[2:])), key)
            else:
                self.assertTrue((PLUGIN / target).is_file(), key)
        for entry in self.manifest["files"]:
            self.assertTrue(list(PLUGIN.glob(entry)), entry)
        self.assertTrue((PLUGIN / self.manifest["icon"]).is_file())
        self.assertNotIn("dependencies", self.manifest)
        self.assertNotIn("scripts", self.manifest)

    def test_patch_names_this_package_and_the_mcp_server(self):
        patch = (PLUGIN / self.manifest["dsh"]["bundle"]["patch"]).read_text()
        self.assertIn(f"name: {self.manifest['name']}\n", patch)
        self.assertIn("serverName: harness2-local", patch)
        self.assertIn(f"{self.manifest['name']}/mcp-server", patch)
        self.assertIn("./mcp-server", self.manifest["exports"])
        # The server is resolved from the installed package, never from a machine path.
        self.assertNotRegex(patch, r"/Users/|/home/|[A-Z]:\\")

    def test_locales_have_title_and_description(self):
        for locale in ("en", "zh"):
            meta = json.loads((PLUGIN / "locale" / f"{locale}.json").read_text())["meta"]
            self.assertTrue(meta["title"])
            self.assertGreater(len(meta["description"]), 40)
            self.assertNotIn("detail", meta)

    def test_skill_overrides_point_at_real_skills(self):
        config = json.loads((PLUGIN / "dsh" / "skills.json").read_text())
        root = (PLUGIN / "dsh" / config["root"]).resolve()
        for directory, override in config["skills"].items():
            self.assertTrue((root / directory / "SKILL.md").is_file(), directory)
            self.assertLessEqual(len(override.get("description", "")), 1024)


@unittest.skipUnless(node_major() >= 22, "Node.js 22+ is required for the provider tests")
class ProviderTests(unittest.TestCase):
    def test_lists_the_skill_with_the_dsh_description(self):
        listed = run_node(
            "import { createProvider } from './dsh/index.js';"
            "const p = await createProvider(); console.log(JSON.stringify(await p.list()))")
        self.assertEqual([c["name"] for c in listed], ["harness2"])
        skill = listed[0]
        self.assertEqual(skill["provider"], "harness2-local")
        self.assertEqual(skill["rank"], 600)
        self.assertTrue(skill["invocation"]["modelInvocable"])
        self.assertNotIn("content", skill)
        self.assertNotIn("every workspace file edit", skill["description"].lower())
        self.assertEqual(Path(skill["resourceBase"]["path"]), PLUGIN / "skills" / "harness2")

    def test_body_is_the_host_notes_plus_the_unchanged_skill(self):
        loaded = run_node(
            "import { createProvider } from './dsh/index.js';"
            "const p = await createProvider(); const [c] = await p.list();"
            "console.log(JSON.stringify(await p.get(c)))")
        source = (PLUGIN / "skills" / "harness2" / "SKILL.md").read_text()
        body = source.split("---\n", 2)[2]
        self.assertTrue(loaded["content"].endswith(body))
        notes = loaded["content"][: -len(body)]
        self.assertIn("mcp__harness2-local__h2_context", notes)
        self.assertIn(str(PLUGIN), notes)
        self.assertNotIn("{{", notes)

    def test_frontmatter_parser(self):
        parsed = run_node(
            "import { parseSkill } from './dsh/index.js';"
            "console.log(JSON.stringify([parseSkill('---\\nname: a-b\\ndescription: \"x: \\\\\"y\\\\\"\"\\n---\\nbody\\n'),"
            " parseSkill('no frontmatter') ?? null]))")
        self.assertEqual(parsed[0], {"fields": {"name": "a-b", "description": 'x: "y"'}, "body": "body\n"})
        self.assertIsNone(parsed[1])


if __name__ == "__main__":
    unittest.main()
