#!/usr/bin/env python3
"""Preview/deploy four owned command hooks; trust only after explicit review."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib

PREFIX = "Harness2 forced assessment"
EVENTS = {"UserPromptSubmit": "user_prompt_submit", "PreToolUse": "pre_tool_use",
          "PostToolUse": "post_tool_use", "Stop": "stop"}
LIMIT = 2 * 1024 * 1024


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def quoted(value):
    return json.dumps(value, ensure_ascii=False)


def safe(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink paths are not accepted")
    return path


def read(path):
    safe(path)
    if not path.exists():
        return b""
    require(path.is_file() and path.stat().st_size <= LIMIT, "Missing/nonregular or oversized input")
    return path.read_bytes()


def atomic_replace(path, data, expected):
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".h2-install-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        require(read(path) == expected, "File changed concurrently; preserve partial installation and review")
        os.replace(temporary, path)
        require(read(path) == data, "Readback mismatch; review partial installation")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def evidence_json(path, value):
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    atomic_replace(path, data, read(path))
    path.chmod(0o600)


def runtime_plan(root, home):
    files = {"gate.py": read(root / "hooks/gate.py"),
             "harness2_local.py": read(root / "server/harness2_local.py")}
    require(all(files.values()), "Bundled gate and engine sources are required")
    hashes = {name: sha(data) for name, data in files.items()}
    combined = sha(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())
    folder = safe(home / "harness2-local/hook-runtime" / combined)
    command = shlex.join([str(Path(sys.executable).resolve()), str(folder / "gate.py"),
                          "--expect-self-sha", hashes["gate.py"],
                          "--expect-engine-sha", hashes["harness2_local.py"]])
    return folder, files, hashes, command


def deploy_runtime(folder, files):
    safe(folder)
    if folder.exists():
        require(folder.is_dir() and {p.name for p in folder.iterdir()} == set(files),
                "Existing runtime bundle has unexpected files; never overwrite")
        require(all(read(folder / name) == data for name, data in files.items()),
                "Existing runtime bundle changed; never overwrite")
        return False
    folder.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".runtime-", dir=folder.parent))
    try:
        for name, data in files.items():
            with (temporary / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            (temporary / name).chmod(0o500 if name == "gate.py" else 0o400)
        require(not folder.exists(), "Runtime appeared concurrently; rerun after review")
        os.rename(temporary, folder)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return True


def is_owned(handler, runtime_root):
    if not isinstance(handler, dict) or not str(handler.get("statusMessage", "")).startswith(PREFIX):
        return False
    require(handler.get("type") == "command", "Owned hook prefix has a conflicting handler type")
    parts = shlex.split(handler.get("command", ""))
    require(len(parts) == 6 and Path(parts[0]).is_absolute()
            and Path(parts[0]).resolve() == Path(sys.executable).resolve()
            and parts[2] == "--expect-self-sha" and parts[4] == "--expect-engine-sha"
            and all(re.fullmatch(r"[a-f0-9]{64}", parts[i]) for i in (3, 5)),
            "Owned hook prefix has an unfamiliar command; do not replace")
    gate = Path(parts[1])
    require(gate.is_absolute() and gate.name == "gate.py"
            and re.fullmatch(r"[a-f0-9]{64}", gate.parent.name)
            and gate.parent.parent == runtime_root, "Owned hook prefix belongs to another runtime")
    declaration = {"gate.py": parts[3], "harness2_local.py": parts[5]}
    require(gate.parent.name == sha(json.dumps(declaration, sort_keys=True, separators=(",", ":")).encode()),
            "Owned runtime path and pinned hashes disagree; preserve and review")
    safe(gate)
    return True


def hook_plan(raw, home, command):
    value = json.loads(raw) if raw else {"hooks": {}}
    require(isinstance(value, dict) and isinstance(value.get("hooks", {}), dict), "Invalid hooks.json")
    groups = value.setdefault("hooks", {})
    own = []
    runtime_root = home / "harness2-local/hook-runtime"
    for event, snake in EVENTS.items():
        entries = groups.setdefault(event, [])
        require(isinstance(entries, list), "Expected event matcher groups")
        found = []
        for gi, group in enumerate(entries):
            require(isinstance(group, dict) and isinstance(group.get("hooks"), list), "Invalid matcher group")
            for hi, handler in enumerate(group["hooks"]):
                if is_owned(handler, runtime_root):
                    found.append((gi, hi))
        require(len(found) <= 1, "Multiple owned hooks for one event; review before replacing")
        handler = {"type": "command", "command": command, "async": False,
                   "timeout": 30, "statusMessage": PREFIX + ": " + event}
        expected_matcher = ".*" if event in ("PreToolUse", "PostToolUse") else None
        if found:
            gi, hi = found[0]
            require(entries[gi].get("matcher") == expected_matcher,
                    "Owned matcher changed; preserve policy and review")
            old = entries[gi]["hooks"][hi]
            require(old.get("enabled", True) is not False and not old.get("async", False),
                    "Owned hook is disabled or asynchronous; do not change its policy")
            entries[gi]["hooks"][hi] = {**old, **handler}
        else:
            gi, hi = len(entries), 0
            group = {"hooks": [handler]}
            if expected_matcher is not None:
                group["matcher"] = expected_matcher
            entries.append(group)
        key = str(home / "hooks.json") + ":" + snake + ":" + str(gi) + ":" + str(hi)
        own.append({"event": event, "key": key, "handler": handler})
    updated = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    # Byte-idempotence when semantic declarations are already the intended ones.
    if raw and json.loads(raw) == value:
        updated = raw
    return updated, own


def config_policy(raw, own):
    config = tomllib.loads(raw.decode())
    features = config.get("features", {})
    require(features.get("hooks", True) is not False and features.get("codex_hooks", True) is not False,
            "Hooks feature is explicitly disabled; do not override policy")
    states = config.get("hooks", {}).get("state", {})
    for item in own:
        require(states.get(item["key"], {}).get("enabled", True) is not False,
                "Owned hook is explicitly disabled; do not override policy")
    return config


def trust_config(raw, hashes):
    """Only append precise owned tables or replace their standalone hash line."""
    config = tomllib.loads(raw.decode())
    states = config.get("hooks", {}).get("state", {})
    updated = raw.decode()
    for key, value in hashes.items():
        old = states.get(key)
        require(old is None or isinstance(old, dict), "Invalid hook trust table")
        require(old is None or old.get("enabled", True) is not False, "Owned hook trust is disabled")
        if old and old.get("trusted_hash") == value:
            continue
        if old is None:
            updated += "\n[hooks.state." + quoted(key) + "]\ntrusted_hash = " + quoted(value) + "\n"
            continue
        # Conservative support: never rewrite inline/multiline or unrelated tables.
        spans = list(re.finditer(r"(?m)^\[[^\r\n]+\][ \t]*(?:#[^\r\n]*)?(?:\r?\n|$)", updated))
        target = None
        for index, header in enumerate(spans):
            try:
                parsed = tomllib.loads(header.group() + "__h2_probe = true\n")
            except tomllib.TOMLDecodeError:
                continue
            table = parsed.get("hooks", {}).get("state", {}).get(key)
            if table == {"__h2_probe": True}:
                target = (header.end(), spans[index + 1].start() if index + 1 < len(spans) else len(updated))
                break
        require(target is not None, "Owned trust uses an unsupported TOML layout; preserve it and review")
        start, end = target
        body = updated[start:end]
        match = re.search(r'''(?m)^(trusted_hash[ \t]*=[ \t]*)("(?:[^"\\\r\n]|\\.)*"|'[^'\r\n]*')([ \t]*(?:#[^\r\n]*)?)(\r?$)''', body)
        if "trusted_hash" in old:
            require(match is not None and len(re.findall(r"(?m)^trusted_hash[ \t]*=", body)) == 1,
                    "Owned trust hash is not a standalone string; preserve it and review")
            body = body[:match.start(2)] + quoted(value) + body[match.end(2):]
        else:
            body += ("" if body.endswith("\n") else "\n") + "trusted_hash = " + quoted(value) + "\n"
        updated = updated[:start] + body + updated[end:]
    after = tomllib.loads(updated)
    expected = copy.deepcopy(config)
    table = expected.setdefault("hooks", {}).setdefault("state", {})
    for key, value in hashes.items():
        table.setdefault(key, {})["trusted_hash"] = value
    require(after == expected, "Unrelated trust settings changed; do not write")
    return updated.encode()


class Native:
    """Only initialize and hooks/list; never starts a thread or model turn."""
    def __init__(self, binary, cwd):
        self.messages, self.counts, self.identifier = queue.Queue(), {}, 0
        self.process = subprocess.Popen([str(binary), "app-server", "--stdio"], cwd=cwd,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        def out():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    pass
        def err():
            for line in self.process.stderr:
                try:
                    record = json.loads(line)
                    key = str(record.get("target", "unknown")) + ":" + str(record.get("level", "unknown"))
                except ValueError:
                    key = "non-json-stderr"
                self.counts[key] = self.counts.get(key, 0) + 1
        threading.Thread(target=out, daemon=True).start()
        threading.Thread(target=err, daemon=True).start()

    def request(self, method, params):
        self.identifier += 1
        self.process.stdin.write(json.dumps({"id": self.identifier, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                result = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise TimeoutError("Native metadata request timed out") from exc
            if result.get("id") == self.identifier:
                require("error" not in result, "Native metadata request failed")
                return result["result"]
        raise TimeoutError("Native metadata request timed out")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


def native_inventory(binary, cwd):
    client = Native(binary, cwd)
    try:
        client.request("initialize", {"clientInfo": {"name": "harness2-hook-installer", "version": "0.4.0"},
                                      "capabilities": {"experimentalApi": True}})
        client.process.stdin.write('{"method":"initialized"}\n')
        client.process.stdin.flush()
        result = client.request("hooks/list", {"cwds": [str(cwd)]})
    finally:
        client.close()
    require(len(result.get("data", [])) == 1 and not result["data"][0].get("errors"),
            "Native hook discovery failed")
    return result["data"][0]["hooks"], client.counts


def matching_inventory(inventory, own, home, command):
    result = {}
    for item in own:
        matches = [hook for hook in inventory if hook.get("key") == item["key"]
                   and hook.get("eventName") == item["event"][0].lower() + item["event"][1:]
                   and hook.get("source") == "user" and hook.get("sourcePath") == str(home / "hooks.json")
                   and hook.get("handlerType") == "command" and hook.get("command") == command
                   and hook.get("async", False) is False]
        require(len(matches) == 1 and matches[0].get("enabled") is True,
                "Owned native hook missing, ambiguous or disabled")
        current = matches[0].get("currentHash", "")
        require(re.fullmatch(r"sha256:[a-f0-9]{64}", current), "Unexpected user hook hash; do not guess trust")
        result[item["key"]] = matches[0]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--trust", action="store_true")
    args = parser.parse_args()
    require(not args.trust or args.apply, "--trust requires explicit --apply")
    root = Path(__file__).resolve().parents[1]
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    require(home.is_absolute(), "CODEX_HOME must be absolute")
    safe(home)
    home = home.resolve()
    hook_path, config_path = home / "hooks.json", home / "config.toml"
    hook_raw, config_raw = read(hook_path), read(config_path)
    folder, files, hashes, command = runtime_plan(root, home)
    hooks, own = hook_plan(hook_raw, home, command)
    config_policy(config_raw, own)
    evidence = safe(Path(args.evidence_dir).expanduser().absolute())
    report = {"applied": False, "verified_active": False, "trust_requested": args.trust,
              "runtime": str(folder), "runtime_hashes": hashes, "command": command,
              "hook_keys": [item["key"] for item in own], "stages": [], "backups": [],
              "other_handlers_semantically_preserved": True, "config_unrelated_bytes_preserved": True,
              "model_calls": 0, "thread_start_calls": 0,
              "execution_verified": False,
              "verification_scope": "Native hooks/list trust and enabled metadata; live enforcement is a separate test",
              "transactional": False, "partial_installation": False}
    evidence_json(evidence / "forced-hooks.candidate.json", {"runtime": str(folder),
                  "runtime_hashes": hashes, "hooks": {item["event"]: item["handler"] for item in own}})
    if args.apply:
        try:
            stamp = str(time.time_ns())
            backup_root = safe(home / "backups" / ("harness2-forced-hooks-" + stamp))
            def backup(path, raw):
                dest = backup_root / (path.name + ".before")
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with dest.open("xb") as stream:
                    stream.write(raw)
                dest.chmod(0o600)
                report["backups"].append(str(dest))
            deploy_runtime(folder, files)
            report["stages"].append("runtime_deployed")
            if hooks != hook_raw:
                backup(hook_path, hook_raw)
                atomic_replace(hook_path, hooks, hook_raw)
            report["stages"].append("hooks_deployed")
            report["applied"] = True
            if args.trust:
                inventory, counts = native_inventory(Path(args.codex_bin).expanduser().resolve(), evidence)
                report["native_stderr_counts"] = counts
                found = matching_inventory(inventory, own, home, command)
                trusted = trust_config(config_raw, {key: value["currentHash"] for key, value in found.items()})
                require(read(hook_path) == hooks, "Hook definitions changed during trust review")
                if trusted != config_raw:
                    backup(config_path, config_raw)
                    atomic_replace(config_path, trusted, config_raw)
                report["stages"].append("owned_trust_written")
                inventory, counts = native_inventory(Path(args.codex_bin).expanduser().resolve(), evidence)
                report["verified_stderr_counts"] = counts
                verified = matching_inventory(inventory, own, home, command)
                require(all(hook.get("trustStatus") == "trusted" for hook in verified.values()),
                        "Owned hooks were deployed but native trust/activation verification failed")
                require(read(hook_path) == hooks and read(config_path) == trusted,
                        "Configuration changed during activation verification")
                deploy_runtime(folder, files)  # Reverify immutable bytes after the native round trip.
                report["verified_active"] = True
                report["verified_hooks"] = [{key: hook.get(key) for key in
                     ("key", "currentHash", "trustStatus", "enabled")} for hook in verified.values()]
        except Exception as exc:
            report["error"] = type(exc).__name__ + ": " + str(exc)
            report["partial_installation"] = bool(report["stages"])
    evidence_json(evidence / "forced-hooks-install.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if "error" in report:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
