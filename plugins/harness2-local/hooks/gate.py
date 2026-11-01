#!/usr/bin/env python3
"""Synchronous Codex lifecycle gate. Receipts are external; native MCP does assessment."""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
class GateDeadline(Exception):
    pass


class WorkspaceIntegrity(Exception):
    pass


LIMIT = 2 * 1024 * 1024
LIGHT = {'h2_context', 'h2_assess', 'h2_recall', 'h2_status'}
CONTROL = {'exec', 'functions.exec', 'tool_search', 'search_tool', 'load_tool_prefix',
           'wait', 'sleep', 'update_plan', 'request_user_input', 'request_user_input_async'}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def require(value):
    if not value:
        raise ValueError('Invalid or stale hook receipt')


def home_path():
    p = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser()
    require(p.is_absolute())
    return p


def no_links(p):
    require(not any(x.is_symlink() for x in (p, *p.parents)))
    return p


def atomic(path, value):
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.gate-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical({'payload': value, 'sha256': sha(canonical(value))}) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_state(path, session, turn):
    no_links(path)
    require(path.is_file() and path.stat().st_size <= LIMIT)
    wrapped = json.loads(path.read_bytes())
    value = wrapped['payload']
    require(wrapped['sha256'] == sha(canonical(value)))
    require(value['schema'] == 1 and value['session'] == session and value['turn'] == turn)
    return value


def project(value):
    p = Path(value).expanduser()
    require(p.is_absolute() and p.is_dir())
    p = p.resolve()
    try:
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS='0')
        result = subprocess.run(['git', '-C', str(p), 'rev-parse', '--show-toplevel'], capture_output=True,
                                text=True, env=env, timeout=3)
        if result.returncode == 0:
            candidate = Path(result.stdout.strip()).resolve()
            if p.is_relative_to(candidate):
                p = candidate
    except (OSError, subprocess.TimeoutExpired):
        pass
    # A home-wide workspace would contain its own sidecar: it is not a project.
    require(not home_path().resolve().is_relative_to(p))
    return p


def native_name(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'mcp__harness2[-_]local__(h2_[a-z_]+)', value)
    return match[1] if match else None


def result_data(value):
    require(isinstance(value, dict) and not value.get('isError'))
    for item in value.get('content', []):
        if item.get('type') == 'text':
            try:
                data = json.loads(item['text'])
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                return data
    raise ValueError('No successful native result')


def tool_input(event):
    value = event.get('tool_input', {})
    if isinstance(value, str):
        value = json.loads(value)
    require(isinstance(value, dict))
    return value


def scoped_project(engine, value, state):
    raw = Path(value).expanduser()
    require(raw.is_absolute() and raw.is_dir())
    raw = raw.resolve()
    for ancestor in (raw, *raw.parents):
        if (ancestor.parent.name == 'workspaces' and ancestor.parent.parent.parent.name == 'runs'
                and ancestor.parent.parent.parent.parent.name == '.harness2'):
            run_id = ancestor.parent.parent.name
            parent = ancestor.parent.parent.parent.parent.parent
            try:
                with engine.locked(str(parent)) as (_, store):
                    _, run = engine.load_run(store, run_id, check_source=True)
                    require(any(Path(c['workspace']).resolve() == ancestor for c in run['candidates'].values()))
                    contract = run['contract']
                    task_key = sha((contract['domain'] + '\n' + ' '.join(contract['task'].split())).encode())[:24]
                    goal = engine.auto_load(store, task_key)
                    require(goal.get('run') == run_id)
                state['workspace_run'] = run_id
                return parent
            except (ValueError, OSError, KeyError) as exc:
                raise WorkspaceIntegrity('Cannot verify the bound experiment workspace') from exc
    return project(str(raw))


def target_project(engine, event, state, inp, native):
    value = inp.get('project') if native else inp.get('workdir', inp.get('cwd'))
    if not value:
        value = state.get('current_project') or event.get('cwd')
    require(isinstance(value, str))
    # A fresh child session can start directly in a candidate workspace.
    if event.get('cwd'):
        scoped_project(engine, event['cwd'], state)
    return scoped_project(engine, value, state)


def automatic_preflight(engine, root, state):
    state['current_project'] = str(root)
    key = sha(str(root).encode())
    if key in state.get('preflights', {}):
        return
    context = engine.dispatch('h2_context', {'project': str(root)})
    # This is an automatic intake assessment, not a semantic claim about the task.
    # Keep raw prompts out of state and keep intake records out of normal goal context.
    task = 'Codex kickoff ' + state['turn'][:24]
    result = engine.dispatch('h2_assess', {'project': str(root), 'task': task,
        'domain': 'codex-kickoff', 'complexity': 'standard',
        'signals': ['Trusted synchronous hook intake before model/tool execution',
                    'Semantic scope remains pending native goal assessment; intake never launches an experiment']})
    with engine.locked(str(root)) as (_, store):
        value = engine.auto_load(store, result['task_key'])
        value['record_kind'] = 'hook-intake'
        engine.auto_save(store, value)
    state.setdefault('preflights', {})[key] = {'project': str(root), 'task_key': result['task_key'],
        'decision': result['decision'], 'context_task_count': len(context['recent_tasks']),
        'recorded_at': now(), 'transport': 'trusted-command-hook/shared-engine',
        'semantic_goal_pending': True}


def instruction(root=None):
    place = str(root) if root else 'a selected project directory outside CODEX_HOME (set tool workdir/project explicitly)'
    return ('Harness² 强制开工门禁：本轮必须先成功调用原生 h2_context，再调用原生 h2_assess，'
            'project=' + place + '。两次真实成功结果经 PostToolUse 复核后，才放行业务工具；'
            '心里判断、旧轮次结果或命令行备用调用不能生成原生门禁凭据。'
            '按上下文恢复原 task/domain/task_key；新目标使用稳定描述，先复用本项目可信经验。'
            'simple/standard且无连续两次失败返回skip：正常实现和反馈，禁止h2_start。'
            '返回start：先读技能；启动前仅可用单条cat/rg --no-config/ls/pwd读取（不使用自定义shell/env或login=true），或apply_patch在项目'
            '/.harness2-preflight/<task_key>/准备冻结输入/检查器，再用assessment=task_key调用h2_start。'
            '门禁记录与锁只写Codex外置状态，指定业务文件限制仍有效。权限拒绝不绕过。')


def deny(event, reason):
    if event == 'PreToolUse':
        return {'hookSpecificOutput': {'hookEventName': event, 'permissionDecision': 'deny',
                                       'permissionDecisionReason': reason}}
    if event in ('UserPromptSubmit', 'Stop'):
        return {'decision': 'block', 'reason': reason}
    return {'systemMessage': reason}


def patch_targets(command, cwd):
    require(isinstance(command, str))
    values = []
    for line in command.splitlines():
        match = re.match(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$', line)
        if match:
            p = Path(match[1])
            p = p if p.is_absolute() else cwd / p
            values.append(p.resolve())
    require(values)
    return values


def preparation_allowed(name, inp, root, key):
    cmd = inp.get('command', inp.get('cmd'))
    if name in ('apply_patch', 'Edit', 'Write'):
        try:
            return all(p.is_relative_to(root / '.harness2-preflight' / key) for p in patch_targets(cmd, root))
        except (ValueError, TypeError):
            return False
    if name in ('Bash', 'exec_command', 'shell_command', 'shell'):
        if inp.get('shell') not in (None, '/bin/sh') or inp.get('login') is True or inp.get('login_shell') is True or inp.get('tty') is True:
            return False
        if any(k in inp for k in ('env', 'env_vars', 'environment', 'shell_env')):
            return False
        if not isinstance(cmd, str) or any(c in cmd for c in ('\n', ';', '|', '&', '>', '<', '`', '$', '\\')):
            return False
        try:
            argv = shlex.split(cmd)
        except ValueError:
            return False
        if not argv or argv[0] not in ('pwd', 'cat', 'ls', 'rg'):
            return False
        # rg can run arbitrary preprocessors; prohibit that family of flags.
        if argv[0] == 'rg':
            if '--no-config' not in argv[1:]:
                return False
            if any(a.startswith(('--pre', '--hostname-bin', '--search-zip'))
                   or (a.startswith('-') and not a.startswith('--') and 'z' in a) for a in argv[1:]):
                return False
        return True
    return name in ('view_image', 'read_file', 'list_directory')


def goal_state(engine, root, item, created):
    require(item.get('context') and item.get('goal') and not item.get('pending'))
    with engine.locked(str(root)) as (_, store):
        value = engine.auto_load(store, item['goal'])
        require(value['assessed_at'] >= item['context']['observed_at'] >= created)
        return value, engine.auto_decision(store, value)


def handle(engine, event, state):
    kind = event['hook_event_name']
    if kind == 'UserPromptSubmit':
        # Prompts can contain credentials: keep a hash, never the raw prompt.
        prompt_hash = sha(str(event.get('prompt', '')).encode())
        if state.get('prompt_sha256') and state['prompt_sha256'] != prompt_hash:
            state.setdefault('revisions', []).append({'prompt_sha256': state['prompt_sha256'],
                'created_at': state['created_at'],
                'goals': {k: v.get('goal') for k, v in state['projects'].items()}})
            require(len(state['revisions']) <= 100)
            state['projects'] = {}
            state['preflights'] = {}
            state.pop('current_project', None)
            state.pop('workspace_run', None)
            state['created_at'] = now()
        state['prompt_sha256'] = prompt_hash
        root = None
        try:
            root = scoped_project(engine, event['cwd'], state)
            state['current_project'] = str(root)
        except (ValueError, KeyError):
            pass
        if root:
            automatic_preflight(engine, root, state)
        return {'hookSpecificOutput': {'hookEventName': kind, 'additionalContext':
                ('Hook intake context/assessment recorded; semantic native goal receipt still required. ' if root else '') + instruction(root)}}
    if kind == 'Stop':
        projects = dict(state['projects'])
        if state.get('current_project'):
            root = project(state['current_project'])
            projects.setdefault(sha(str(root).encode()), {'project': str(root)})
        for item in projects.values():
            root = project(item['project'])
            try:
                _, decision = goal_state(engine, root, item, state['created_at'])
                require(decision['decision'] != 'blocked')
                if decision['decision'] == 'start':
                    return deny(kind, 'Harness² assessed a project as start but no bound run exists. Prepare frozen checks and call native h2_start before claiming completion.')
            except (ValueError, OSError, KeyError):
                return deny(kind, instruction(root))
        return {}
    inp = tool_input(event)
    name = event.get('tool_name', '')
    native = native_name(name)
    if kind == 'PostToolUse':
        if native not in ('h2_context', 'h2_assess'):
            return {}
        root = target_project(engine, event, state, inp, native)
        require(str(root) == str(Path(inp['project']).resolve()))
        key = sha(str(root).encode())
        item = state['projects'].setdefault(key, {'project': str(root)})
        try:
            pending = item.get('pending')
            if pending:
                require(pending.get('tool') == native)
                if pending.get('tool_use_id') is not None:
                    require(pending['tool_use_id'] == event['tool_use_id'])
            result = result_data(event.get('tool_response'))
            require(result.get('metadata_external') is True)
            if native == 'h2_context':
                require(result['project'] == str(root))
                item.setdefault('context', {'observed_at': now(), 'result_sha256': sha(canonical(result))})
                item['last_context_sha256'] = sha(canonical(result))
            else:
                require(item.get('context'))
                with engine.locked(str(root)) as (_, store):
                    value = engine.auto_load(store, result['task_key'])
                    require(value['task'] == inp['task'].strip() and value['domain'] == inp['domain'])
                    require(value['complexity'] == inp['complexity'])
                    require(value['assessed_at'] >= item['context']['observed_at'])
                    fresh = engine.auto_decision(store, value)
                    require(fresh['decision'] == result['decision'])
                item.update(goal=value['task_key'], assessment_result_sha256=sha(canonical(result)))
            item.pop('pending', None)
            state['current_project'] = str(root)
            return {}
        except (ValueError, OSError, KeyError, TypeError):
            # A failed/old/foreign result cannot keep a previous grant alive.
            item.pop('goal', None)
            item['pending'] = {'tool': native, 'failed': True}
            return {'systemMessage': 'Harness² native result did not grant a gate receipt; run fresh context then assessment for this project.'}
    if kind != 'PreToolUse':
        raise ValueError('Unsupported hook event')
    if name in CONTROL:
        return {}
    if native in LIGHT:
        root = target_project(engine, event, state, inp, native)
        automatic_preflight(engine, root, state)
        if native in ('h2_context', 'h2_assess'):
            item = state['projects'].setdefault(sha(str(root).encode()), {'project': str(root)})
            if native == 'h2_assess':
                if not item.get('context') or item.get('pending'):
                    return deny(kind, instruction(root))
                item.pop('goal', None)
            item['pending'] = {'tool': native, 'tool_use_id': event.get('tool_use_id')}
        return {}
    root = target_project(engine, event, state, inp, native)
    automatic_preflight(engine, root, state)
    item = state['projects'].get(sha(str(root).encode()), {})
    try:
        value, decision = goal_state(engine, root, item, state['created_at'])
    except (ValueError, OSError, KeyError):
        return deny(kind, instruction(root))
    route = decision['decision']
    if native == 'h2_feedback':
        if inp.get('task_key') != value['task_key']:
            return deny(kind, 'Feedback must name the assessed current goal; restore its context before reporting outcomes.')
        return {}  # Recording real outcomes must remain possible before start/closeout.
    if route == 'blocked':
        if native in ('h2_start', 'h2_probe', 'h2_adopt', 'h2_propose', 'h2_reflect'):
            return deny(kind, 'Harness² retained evidence is blocked; preserve failed/UNKNOWN evidence and do not restart or replay.')
        return {'hookSpecificOutput': {'hookEventName': kind, 'additionalContext':
            'Goal assessment is recorded but its experiment is blocked. Diagnose within the original authorization, preserve failure/UNKNOWN evidence, and run actual outer checks for explicit closeout. Never replay or claim experiment completion.'}}
    if native == 'h2_start':
        if state.get('workspace_run') and value.get('run') != state['workspace_run']:
            return deny(kind, 'Verified candidate workspaces cannot create a nested experiment; resume only the parent bound run.')
        if route not in ('start', 'resume', 'reuse'):
            return deny(kind, 'Harness² simple/standard assessment selected skip: h2_start is forbidden; perform ordinary checks and feedback only.')
        if inp.get('assessment') != value['task_key']:
            return deny(kind, 'h2_start must bind assessment to this turn/project task_key; unbound experiments are forbidden.')
        return {}
    if native in ('h2_probe', 'h2_adopt', 'h2_propose', 'h2_reflect'):
        if not value.get('run') or inp.get('run') != value['run']:
            return deny(kind, 'Experiment tool must use the assessed goal bound run; skip tasks cannot execute experiments.')
        return {}
    if route == 'start':
        if preparation_allowed(name, inp, root, value['task_key']):
            return {}
        return deny(kind, 'Harness² requires a bound h2_start before business implementation. Read with a single cat/rg --no-config/ls/pwd without custom shell/env/login=true; use apply_patch only in .harness2-preflight/' + value['task_key'] + '/ to prepare frozen checks.')
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine')
    parser.add_argument('--expect-self-sha')
    parser.add_argument('--expect-engine-sha')
    parser.add_argument('--deadline-seconds', type=int, default=8)
    args = parser.parse_args()
    event = {}
    kind = 'PreToolUse'
    def deadline(signum, frame):
        raise GateDeadline('Internal gate deadline')
    try:
        require(1 <= args.deadline_seconds <= 15)
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(args.deadline_seconds)
        raw = sys.stdin.buffer.read(LIMIT + 1)
        require(len(raw) <= LIMIT)
        event = json.loads(raw)
        kind = event.get('hook_event_name', kind)
        require(kind in ('UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop'))
        for key in ('session_id', 'turn_id'):
            require(isinstance(event.get(key), str) and 1 <= len(event[key]) <= 300)
        engine_path = Path(args.engine) if args.engine else Path(__file__).with_name('harness2_local.py')
        if args.expect_self_sha:
            require(sha(Path(__file__).read_bytes()) == args.expect_self_sha)
        if args.expect_engine_sha:
            require(sha(engine_path.read_bytes()) == args.expect_engine_sha)
        spec = importlib.util.spec_from_file_location('harness2_gate_engine', engine_path)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        session = sha(event['session_id'].encode()); turn = sha(event['turn_id'].encode())
        base = no_links(home_path() / 'harness2-local/hook-gates' / session)
        base.mkdir(parents=True, mode=0o700, exist_ok=True)
        lock = no_links(base / 'lock')
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'a+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            path = no_links(base / (turn + '.json'))
            if path.exists():
                state = read_state(path, session, turn)
            else:
                state = {'schema': 1, 'session': session, 'turn': turn, 'created_at': now(), 'projects': {}}
            output = handle(engine, event, state)
            receipt_event = {'event': kind, 'tool': event.get('tool_name'), 'at': now(),
                'workspace_run': state.get('workspace_run'),
                'decision': output.get('hookSpecificOutput', {}).get('permissionDecision', output.get('decision', 'continue'))}
            state.setdefault('events', []).append(receipt_event)
            require(len(state['events']) <= 4096)
            atomic(path, state)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Ordinary hook errors are fail-open in Codex. Return a valid explicit deny.
        reason = 'Harness² hook cannot verify the current assessment (' + type(exc).__name__ + '); no business tool may proceed. Restore the reviewed hook and reassess.'
        print(json.dumps(deny(kind, reason), ensure_ascii=False))
        if kind == 'PostToolUse':
            return 0
        print(reason, file=sys.stderr)
        return 2
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
