#!/usr/bin/env python3
"""CodeCompass for Android (Pydroid 3 edition).

HOW TO USE
1. Save this file inside the project folder you want to organize
   (or edit PROJECT_ROOT below to point at it).
2. Open this file in Pydroid 3 and tap Run.
3. Open the link it prints (something like http://127.0.0.1:8000) in your
   phone's browser.
4. To stop it, go back to Pydroid and tap Stop.

Uses only the Python standard library - no pip installs needed.
"""

import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Configuration - edit these if you need to
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.environ.get('CODECOMPASS_ROOT') or os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('CODECOMPASS_PORT', '8000'))
SELF_FILENAME = os.path.basename(__file__)

# ---------------------------------------------------------------------------
# Project scanning: TODO/FIXME markers + language/LOC stats
# ---------------------------------------------------------------------------
IGNORED_DIRS = {
    '.git', 'node_modules', 'dist', 'build', 'out', '.next', '.nuxt',
    'vendor', 'target', '.venv', 'venv', '__pycache__', 'coverage',
    '.codecompass', '.cache', '.gradle', '.idea'
}

LANGUAGES = {
    '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript', '.ts': 'TypeScript',
    '.tsx': 'TypeScript', '.rb': 'Ruby', '.go': 'Go', '.rs': 'Rust', '.java': 'Java',
    '.kt': 'Kotlin', '.c': 'C', '.cc': 'C++', '.cpp': 'C++', '.h': 'C/C++ Header',
    '.hpp': 'C/C++ Header', '.cs': 'C#', '.php': 'PHP', '.swift': 'Swift',
    '.sh': 'Shell', '.bash': 'Shell', '.md': 'Markdown', '.yml': 'YAML',
    '.yaml': 'YAML', '.json': 'JSON', '.html': 'HTML', '.css': 'CSS',
    '.sql': 'SQL', '.txt': 'Text'
}

TAG_RE = re.compile(r'\b(TODO|FIXME|HACK|XXX|BUG)\b:?\s*(.*)')
MAX_FILES = 6000
MAX_FILE_SIZE = 2 * 1024 * 1024


def is_binary(sample):
    return b'\x00' in sample[:512]


def scan_project(root):
    by_language = {}
    todos = []
    total_files = 0
    total_lines = 0
    count = 0
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not (d.startswith('.') and d not in IGNORED_DIRS)]

        for filename in filenames:
            if count >= MAX_FILES:
                truncated = True
                break
            count += 1
            ext = os.path.splitext(filename)[1].lower()
            lang = LANGUAGES.get(ext)
            if not lang:
                continue
            full = os.path.join(dirpath, filename)
            try:
                if os.path.getsize(full) > MAX_FILE_SIZE:
                    continue
                with open(full, 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            if is_binary(data):
                continue
            try:
                content = data.decode('utf-8')
            except UnicodeDecodeError:
                continue

            lines = content.split('\n')
            total_files += 1
            total_lines += len(lines)

            entry = by_language.setdefault(lang, {'language': lang, 'files': 0, 'lines': 0})
            entry['files'] += 1
            entry['lines'] += len(lines)

            rel_path = os.path.relpath(full, root).replace(os.sep, '/')
            for i, line in enumerate(lines):
                m = TAG_RE.search(line)
                if m:
                    todos.append({
                        'file': rel_path,
                        'line': i + 1,
                        'tag': m.group(1).upper(),
                        'text': m.group(2).strip()[:240]
                    })
        if count >= MAX_FILES:
            break

    languages = sorted(by_language.values(), key=lambda entry: -entry['lines'])
    return {
        'stats': {
            'totalFiles': total_files,
            'totalLines': total_lines,
            'languages': languages,
            'truncated': truncated
        },
        'todos': todos
    }


# ---------------------------------------------------------------------------
# Git info (best-effort - Android/Pydroid usually has no git binary at all)
# ---------------------------------------------------------------------------
UNIT_SEP = chr(31)


def run_git(root, args):
    try:
        result = subprocess.run(
            ['git'] + args, cwd=root, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def get_git_info(root):
    inside = run_git(root, ['rev-parse', '--is-inside-work-tree'])
    if inside != 'true':
        return {'isRepo': False}

    branch = run_git(root, ['rev-parse', '--abbrev-ref', 'HEAD']) or 'HEAD'

    status_raw = run_git(root, ['status', '--porcelain']) or ''
    status = [
        {'state': line[:2].strip(), 'path': line[3:]}
        for line in status_raw.split('\n') if line
    ]

    log_format = '%h' + UNIT_SEP + '%an' + UNIT_SEP + '%ar' + UNIT_SEP + '%s'
    log_raw = run_git(root, ['log', '-20', '--pretty=format:' + log_format]) or ''
    log = []
    for line in log_raw.split('\n'):
        if not line:
            continue
        parts = line.split(UNIT_SEP)
        parts += [''] * (4 - len(parts))
        log.append({'hash': parts[0], 'author': parts[1], 'date': parts[2], 'message': parts[3]})

    return {'isRepo': True, 'branch': branch, 'status': status, 'log': log}


# ---------------------------------------------------------------------------
# Kanban board persistence (.codecompass/board.json)
# ---------------------------------------------------------------------------
DEFAULT_COLUMNS = [
    {'id': 'todo', 'title': 'To Do'},
    {'id': 'doing', 'title': 'In Progress'},
    {'id': 'done', 'title': 'Done'}
]


def codecompass_dir(root):
    return os.path.join(root, '.codecompass')


def board_path(root):
    return os.path.join(codecompass_dir(root), 'board.json')


def default_board():
    return {'columns': DEFAULT_COLUMNS, 'tasks': []}


def load_board(root):
    path = board_path(root)
    if not os.path.exists(path):
        return default_board()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault('columns', DEFAULT_COLUMNS)
        data.setdefault('tasks', [])
        return data
    except (OSError, ValueError):
        return default_board()


def save_board(root, board):
    d = codecompass_dir(root)
    os.makedirs(d, exist_ok=True)
    with open(board_path(root), 'w', encoding='utf-8') as f:
        json.dump(board, f, indent=2)


def make_id():
    return format(int(time.time() * 1000), 'x') + format(int.from_bytes(os.urandom(4), 'big'), 'x')[:6]


def add_task(root, title, column='todo', tag='', notes=''):
    board = load_board(root)
    valid_column = column if any(c['id'] == column for c in board['columns']) else board['columns'][0]['id']
    task = {
        'id': make_id(),
        'title': str(title or 'Untitled task')[:300],
        'column': valid_column,
        'notes': str(notes or '')[:2000],
        'tag': str(tag or '')[:100],
        'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }
    board['tasks'].append(task)
    save_board(root, board)
    return task


def update_task(root, task_id, fields):
    board = load_board(root)
    task = next((t for t in board['tasks'] if t['id'] == task_id), None)
    if not task:
        return None
    if isinstance(fields.get('title'), str):
        task['title'] = fields['title'][:300]
    if isinstance(fields.get('notes'), str):
        task['notes'] = fields['notes'][:2000]
    if isinstance(fields.get('column'), str) and any(c['id'] == fields['column'] for c in board['columns']):
        task['column'] = fields['column']
    save_board(root, board)
    return task


def delete_task(root, task_id):
    board = load_board(root)
    before = len(board['tasks'])
    board['tasks'] = [t for t in board['tasks'] if t['id'] != task_id]
    removed = len(board['tasks']) != before
    if removed:
        save_board(root, board)
    return removed


# ---------------------------------------------------------------------------
# Notes scratchpad (.codecompass/notes.md)
# ---------------------------------------------------------------------------
DEFAULT_NOTES = '# Project Notes\n\nJot down decisions, context for future-you, or anything worth remembering.\n'


def notes_path(root):
    return os.path.join(codecompass_dir(root), 'notes.md')


def get_notes(root):
    path = notes_path(root)
    if not os.path.exists(path):
        return DEFAULT_NOTES
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return DEFAULT_NOTES


def save_notes(root, content):
    d = codecompass_dir(root)
    os.makedirs(d, exist_ok=True)
    with open(notes_path(root), 'w', encoding='utf-8') as f:
        f.write(str(content)[:200000])


# ---------------------------------------------------------------------------
# Project health checklist
# ---------------------------------------------------------------------------
def exists_rel(root, rel):
    return os.path.exists(os.path.join(root, rel))


def any_exists(root, rels):
    return any(exists_rel(root, r) for r in rels)


def is_git_repo(root):
    return run_git(root, ['rev-parse', '--is-inside-work-tree']) == 'true'


def has_commits(root):
    return run_git(root, ['rev-parse', 'HEAD']) is not None


def get_health(root):
    checks = []

    checks.append({
        'id': 'readme', 'label': 'README present',
        'status': 'pass' if any_exists(root, ['README.md', 'README', 'readme.md']) else 'fail',
        'detail': 'A README helps anyone (including future you) understand the project quickly.'
    })
    checks.append({
        'id': 'license', 'label': 'License present',
        'status': 'pass' if any_exists(root, ['LICENSE', 'LICENSE.md', 'LICENSE.txt']) else 'warn',
        'detail': 'Clarifies how others are allowed to use the code.'
    })
    checks.append({
        'id': 'gitignore', 'label': '.gitignore present',
        'status': 'pass' if exists_rel(root, '.gitignore') else 'warn',
        'detail': 'Keeps build artifacts and secrets out of version control.'
    })

    git = is_git_repo(root)
    checks.append({
        'id': 'git-repo', 'label': 'Git repository initialized',
        'status': 'pass' if git else 'warn',
        'detail': 'Version control is a safety net. Not required on this device if git is unavailable.'
    })
    if git:
        checks.append({
            'id': 'git-commits', 'label': 'Has at least one commit',
            'status': 'pass' if has_commits(root) else 'warn',
            'detail': 'An empty repo means nothing is actually saved yet.'
        })

    ci_paths = ['.github/workflows', '.gitlab-ci.yml', '.circleci/config.yml']
    checks.append({
        'id': 'ci', 'label': 'CI configuration present',
        'status': 'pass' if any_exists(root, ci_paths) else 'warn',
        'detail': 'Automated checks catch regressions before they reach main.'
    })

    checks.append({
        'id': 'deps', 'label': 'Dependency file present (requirements.txt / Pipfile / pyproject.toml)',
        'status': 'pass' if any_exists(root, ['requirements.txt', 'Pipfile', 'pyproject.toml']) else 'warn',
        'detail': 'Lists what your project depends on so it can be reproduced elsewhere.'
    })

    checks.append({
        'id': 'test-dir', 'label': 'Tests directory present',
        'status': 'pass' if any_exists(root, ['test', 'tests', '__tests__']) else 'warn',
        'detail': 'A dedicated place for tests keeps them discoverable.'
    })

    pass_count = sum(1 for c in checks if c['status'] == 'pass')
    return {'checks': checks, 'passCount': pass_count, 'total': len(checks)}


# ---------------------------------------------------------------------------
# Script runner: local .py files, plus optional codecompass_scripts.json
# ---------------------------------------------------------------------------
def list_py_scripts(root):
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        entries = []
    scripts = []
    for name in entries:
        if not name.endswith('.py') or name == SELF_FILENAME:
            continue
        full = os.path.join(root, name)
        if not os.path.isfile(full):
            continue
        scripts.append({'type': 'python', 'id': 'py:' + name, 'name': name, 'command': 'python ' + name})
    return scripts


def list_custom_scripts(root):
    path = os.path.join(root, 'codecompass_scripts.json')
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    scripts = []
    if isinstance(data, dict):
        for name, command in data.items():
            if isinstance(command, str):
                scripts.append({'type': 'custom', 'id': 'custom:' + name, 'name': name, 'command': command})
    return scripts


def list_runnables(root):
    return list_custom_scripts(root) + list_py_scripts(root)


def find_runnable(root, runnable_id):
    for r in list_runnables(root):
        if r['id'] == runnable_id:
            return r
    return None


def start_runnable_process(root, runnable):
    if runnable['type'] == 'python':
        name = runnable['id'][len('py:'):]
        args = [sys.executable, name]
    else:
        args = shlex.split(runnable['command'])
    return subprocess.Popen(
        args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )


# ---------------------------------------------------------------------------
# Frontend (embedded so this is a single downloadable file)
# ---------------------------------------------------------------------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CodeCompass</title>
<link rel="stylesheet" href="/style.css" />
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">&#8982;</span>
        <span class="brand-name">CodeCompass</span>
      </div>
      <div class="project-path" id="project-path">loading project…</div>
      <nav class="tabs" id="tabs">
        <button class="tab active" data-tab="overview">Overview</button>
        <button class="tab" data-tab="todos">TODOs</button>
        <button class="tab" data-tab="board">Board</button>
        <button class="tab" data-tab="scripts">Scripts</button>
        <button class="tab" data-tab="health">Health</button>
        <button class="tab" data-tab="notes">Notes</button>
        <button class="tab" data-tab="git">Git</button>
      </nav>
      <button class="palette-btn" id="palette-btn" title="Command palette">Menu</button>
    </header>

    <main class="content">
      <section id="panel-overview" class="panel active">
        <div class="cards" id="stat-cards"></div>
        <div class="card lang-card">
          <h3>Languages</h3>
          <div id="lang-bars" class="lang-bars"></div>
        </div>
      </section>

      <section id="panel-todos" class="panel">
        <div class="panel-head">
          <h2>TODO / FIXME markers</h2>
          <span class="hint">Tap "+ Board" to send a marker to your kanban board.</span>
        </div>
        <div id="todo-list" class="todo-list"></div>
      </section>

      <section id="panel-board" class="panel">
        <div class="panel-head">
          <h2>Kanban Board</h2>
          <div class="board-actions">
            <form id="add-task-form" class="add-task-form">
              <input type="text" id="new-task-title" placeholder="Add a task…" required />
              <button type="submit">Add</button>
            </form>
            <a id="board-export-link" class="export-link" href="/api/board/export" download="board.md">Export as Markdown</a>
          </div>
        </div>
        <div id="board-columns" class="board-columns"></div>
      </section>

      <section id="panel-scripts" class="panel">
        <div class="panel-head">
          <h2>Scripts</h2>
          <span class="hint">Any .py file in the project folder, plus commands in codecompass_scripts.json.</span>
        </div>
        <div id="scripts-list" class="scripts-list"></div>
        <div id="scripts-console" class="scripts-console hidden">
          <div class="scripts-console-head">
            <span id="scripts-console-title">Running…</span>
            <button id="scripts-console-stop">Stop</button>
          </div>
          <pre id="scripts-console-output"></pre>
        </div>
      </section>

      <section id="panel-health" class="panel">
        <div class="panel-head">
          <h2>Project Health</h2>
        </div>
        <div id="health-content"></div>
      </section>

      <section id="panel-notes" class="panel">
        <div class="panel-head">
          <h2>Notes</h2>
          <span class="hint" id="notes-status">Saved to .codecompass/notes.md</span>
        </div>
        <textarea id="notes-editor" class="notes-editor" spellcheck="false"></textarea>
      </section>

      <section id="panel-git" class="panel">
        <div class="panel-head">
          <h2>Git Activity</h2>
        </div>
        <div id="git-content"></div>
      </section>
    </main>
  </div>

  <div id="palette-overlay" class="palette-overlay hidden">
    <div class="palette">
      <input type="text" id="palette-input" class="palette-input" placeholder="Jump to a tab or run a script…" />
      <div id="palette-results" class="palette-results"></div>
    </div>
  </div>

  <script src="/app.js"></script>
</body>
</html>
"""

STYLE_CSS = """:root {
  --bg: #0f1117;
  --bg-elevated: #161925;
  --bg-card: #1b1f2e;
  --border: #2a2f42;
  --text: #e6e8ef;
  --text-dim: #9096ab;
  --accent: #7c9eff;
  --accent-soft: rgba(124, 158, 255, 0.15);
  --green: #66d9a3;
  --amber: #f2c14e;
  --red: #f2777a;
  --radius: 10px;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg: #f5f6fa;
    --bg-elevated: #ffffff;
    --bg-card: #ffffff;
    --border: #e2e5ee;
    --text: #1c2030;
    --text-dim: #666d84;
    --accent: #4468e0;
    --accent-soft: rgba(68, 104, 224, 0.1);
  }
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
}

.app { display: flex; flex-direction: column; min-height: 100vh; }

.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 14px 24px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 18px; }
.brand-mark { color: var(--accent); font-size: 22px; }

.project-path {
  color: var(--text-dim);
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 120px;
}

.tabs { display: flex; gap: 4px; flex-wrap: wrap; }

.tab {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-dim);
  padding: 8px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}

.tab:hover { background: var(--accent-soft); color: var(--text); }
.tab.active { background: var(--accent-soft); color: var(--accent); }

.content { padding: 24px; max-width: 1100px; width: 100%; margin: 0 auto; flex: 1; }

.panel { display: none; }
.panel.active { display: block; }

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.panel-head h2 { margin: 0; font-size: 18px; }
.hint { color: var(--text-dim); font-size: 13px; }

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
}

.stat-card .stat-value { font-size: 28px; font-weight: 700; }
.stat-card .stat-label { color: var(--text-dim); font-size: 13px; margin-top: 4px; }

.lang-card h3 { margin: 0 0 14px; font-size: 15px; }

.lang-bars { display: flex; flex-direction: column; gap: 10px; }

.lang-row { display: grid; grid-template-columns: 120px 1fr 90px; align-items: center; gap: 10px; font-size: 13px; }
.lang-row .lang-name { color: var(--text); }
.lang-row .lang-meta { color: var(--text-dim); text-align: right; }

.bar-track { background: var(--border); border-radius: 6px; height: 8px; overflow: hidden; }
.bar-fill { background: var(--accent); height: 100%; border-radius: 6px; }

.todo-list { display: flex; flex-direction: column; gap: 8px; }

.todo-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  flex-wrap: wrap;
}

.todo-tag {
  font-weight: 700;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent);
  flex-shrink: 0;
}
.todo-tag.FIXME, .todo-tag.BUG { background: rgba(242, 119, 122, 0.15); color: var(--red); }
.todo-tag.HACK, .todo-tag.XXX { background: rgba(242, 193, 78, 0.15); color: var(--amber); }

.todo-location {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--text-dim);
  flex-shrink: 0;
}

.todo-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.todo-add-btn {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.todo-add-btn:hover { border-color: var(--accent); color: var(--accent); }

.empty-state { color: var(--text-dim); font-size: 14px; padding: 20px 0; }

.add-task-form { display: flex; gap: 8px; flex-wrap: wrap; }
.add-task-form input {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  color: var(--text);
  font-size: 14px;
  min-width: 180px;
}
.add-task-form button {
  background: var(--accent);
  border: none;
  color: #0f1117;
  font-weight: 600;
  border-radius: 8px;
  padding: 8px 16px;
  cursor: pointer;
}

.board-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

@media (max-width: 800px) {
  .board-columns { grid-template-columns: 1fr; }
}

.board-column {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  min-height: 200px;
}

.board-column.drag-over { border-color: var(--accent); background: var(--accent-soft); }

.board-column-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-dim);
}

.task-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: grab;
  font-size: 13px;
}

.task-card.dragging { opacity: 0.4; }
.task-card .task-title { margin-bottom: 4px; }
.task-card .task-meta { display: flex; justify-content: space-between; align-items: center; }
.task-card .task-tag { color: var(--accent); font-size: 11px; font-family: ui-monospace, monospace; }
.task-card .task-remove { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.task-card .task-remove:hover { color: var(--red); }

.git-branch {
  display: inline-block;
  background: var(--accent-soft);
  color: var(--accent);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 16px;
}

.git-section { margin-bottom: 24px; }
.git-section h3 { font-size: 14px; color: var(--text-dim); margin-bottom: 10px; }

.commit-row {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  flex-wrap: wrap;
}
.commit-hash { font-family: ui-monospace, monospace; color: var(--accent); flex-shrink: 0; }
.commit-message { flex: 1; }
.commit-meta { color: var(--text-dim); flex-shrink: 0; }

.status-row {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  font-size: 13px;
  font-family: ui-monospace, monospace;
}
.status-state { color: var(--amber); width: 28px; flex-shrink: 0; }

.palette-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
  flex-shrink: 0;
}
.palette-btn:hover { border-color: var(--accent); color: var(--accent); }

.board-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.export-link { color: var(--accent); font-size: 13px; text-decoration: none; }
.export-link:hover { text-decoration: underline; }

.scripts-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }

.script-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  flex-wrap: wrap;
}

.script-type {
  font-weight: 700;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent);
  flex-shrink: 0;
  text-transform: uppercase;
}

.script-name { font-weight: 600; flex-shrink: 0; }
.script-command {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--text-dim);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 80px;
}

.script-run-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}
.script-run-btn:hover { border-color: var(--green); color: var(--green); }
.script-run-btn:disabled { opacity: 0.5; cursor: default; }

.scripts-console {
  background: #0a0c12;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.scripts-console.hidden { display: none; }

.scripts-console-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-dim);
}
.scripts-console-head button {
  background: rgba(242, 119, 122, 0.15);
  color: var(--red);
  border: none;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}

.scripts-console pre {
  margin: 0;
  padding: 14px;
  max-height: 360px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.5;
  color: #d8dcec;
  white-space: pre-wrap;
  word-break: break-word;
}

.health-summary { font-size: 15px; margin-bottom: 16px; color: var(--text-dim); }
.health-summary strong { color: var(--text); }

.health-check {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 8px;
}

.health-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  margin-top: 1px;
}
.health-icon.pass { background: rgba(102, 217, 163, 0.15); color: var(--green); }
.health-icon.warn { background: rgba(242, 193, 78, 0.15); color: var(--amber); }
.health-icon.fail { background: rgba(242, 119, 122, 0.15); color: var(--red); }

.health-body .health-label { font-weight: 600; font-size: 14px; }
.health-body .health-detail { color: var(--text-dim); font-size: 12.5px; margin-top: 2px; }

.notes-editor {
  width: 100%;
  min-height: 60vh;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 16px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13.5px;
  line-height: 1.6;
  resize: vertical;
}
.notes-editor:focus { outline: none; border-color: var(--accent); }

.palette-overlay {
  position: fixed;
  inset: 0;
  background: rgba(10, 12, 18, 0.55);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 12vh;
  z-index: 100;
}
.palette-overlay.hidden { display: none; }

.palette {
  width: min(560px, 92vw);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
}

.palette-input {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--border);
  padding: 16px 18px;
  color: var(--text);
  font-size: 15px;
}
.palette-input:focus { outline: none; }

.palette-results { max-height: 320px; overflow-y: auto; padding: 6px; }

.palette-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}
.palette-item.active { background: var(--accent-soft); }
.palette-item .palette-item-label { color: var(--text); }
.palette-item .palette-item-hint { color: var(--text-dim); font-size: 12px; }
"""

APP_JS = """(function () {
  'use strict';

  const state = {
    scan: null,
    git: null,
    board: null,
    scripts: null,
    health: null,
    activeRun: null
  };

  const TAB_NAMES = ['overview', 'todos', 'board', 'scripts', 'health', 'notes', 'git'];

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function fetchJson(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error('Request failed: ' + url);
    return res.json();
  }

  function switchTab(name) {
    if (TAB_NAMES.indexOf(name) === -1) return;
    $all('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
    $all('.panel').forEach((p) => p.classList.toggle('active', p.id === 'panel-' + name));
  }

  function setupTabs() {
    $all('.tab').forEach((tab) => {
      tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
  }

  function renderOverview() {
    const { scan, git, board } = state;
    if (!scan) return;

    const openTasks = board ? board.tasks.filter((t) => t.column !== 'done').length : 0;

    const cards = [
      { value: scan.stats.totalFiles, label: 'Files scanned' },
      { value: scan.stats.totalLines.toLocaleString(), label: 'Lines of code' },
      { value: scan.todos.length, label: 'TODO / FIXME markers' },
      { value: git && git.isRepo ? git.status.length : '—', label: 'Uncommitted changes' },
      { value: openTasks, label: 'Open board tasks' }
    ];

    $('#stat-cards').innerHTML = cards
      .map((c) => '<div class="card stat-card"><div class="stat-value">' + c.value + '</div><div class="stat-label">' + c.label + '</div></div>')
      .join('');

    const maxLines = Math.max(1, ...scan.stats.languages.map((l) => l.lines));
    $('#lang-bars').innerHTML = scan.stats.languages
      .slice(0, 10)
      .map((l) => {
        const pct = Math.round((l.lines / maxLines) * 100);
        return (
          '<div class="lang-row">' +
          '<div class="lang-name">' + escapeHtml(l.language) + '</div>' +
          '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
          '<div class="lang-meta">' + l.files + ' files</div>' +
          '</div>'
        );
      })
      .join('') || '<div class="empty-state">No recognized source files found.</div>';
  }

  function renderTodos() {
    const { scan } = state;
    if (!scan) return;
    if (!scan.todos.length) {
      $('#todo-list').innerHTML = '<div class="empty-state">No TODO/FIXME/HACK/XXX/BUG markers found. Nice and tidy.</div>';
      return;
    }
    $('#todo-list').innerHTML = scan.todos
      .map((t, i) => (
        '<div class="todo-item">' +
        '<span class="todo-tag ' + escapeHtml(t.tag) + '">' + escapeHtml(t.tag) + '</span>' +
        '<span class="todo-location">' + escapeHtml(t.file) + ':' + t.line + '</span>' +
        '<span class="todo-text">' + escapeHtml(t.text || '') + '</span>' +
        '<button class="todo-add-btn" data-idx="' + i + '">+ Board</button>' +
        '</div>'
      ))
      .join('');

    $all('.todo-add-btn', $('#todo-list')).forEach((btn) => {
      btn.addEventListener('click', async () => {
        const t = scan.todos[Number(btn.dataset.idx)];
        btn.disabled = true;
        btn.textContent = 'Added';
        await fetchJson('/api/board/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: (t.text || (t.tag + ' marker')).slice(0, 200),
            column: 'todo',
            tag: t.file + ':' + t.line
          })
        });
        state.board = await fetchJson('/api/board');
        renderBoard();
      });
    });
  }

  function renderBoard() {
    const { board } = state;
    if (!board) return;

    $('#board-columns').innerHTML = board.columns
      .map((col) => {
        const tasks = board.tasks.filter((t) => t.column === col.id);
        const taskHtml = tasks
          .map((t) => (
            '<div class="task-card" draggable="true" data-id="' + t.id + '">' +
            '<div class="task-title">' + escapeHtml(t.title) + '</div>' +
            '<div class="task-meta">' +
            '<span class="task-tag">' + escapeHtml(t.tag || '') + '</span>' +
            '<button class="task-remove" data-id="' + t.id + '">remove</button>' +
            '</div>' +
            '</div>'
          ))
          .join('');
        return (
          '<div class="board-column" data-column="' + col.id + '">' +
          '<div class="board-column-head"><span>' + escapeHtml(col.title) + '</span><span>' + tasks.length + '</span></div>' +
          '<div class="board-column-body">' + taskHtml + '</div>' +
          '</div>'
        );
      })
      .join('');

    setupDragAndDrop();

    $all('.task-remove').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch('/api/board/tasks/' + btn.dataset.id, { method: 'DELETE' });
        state.board = await fetchJson('/api/board');
        renderBoard();
        renderOverview();
      });
    });
  }

  function setupDragAndDrop() {
    $all('.task-card').forEach((card) => {
      card.addEventListener('dragstart', () => {
        card.classList.add('dragging');
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
      });
    });

    $all('.board-column').forEach((col) => {
      col.addEventListener('dragover', (e) => {
        e.preventDefault();
        col.classList.add('drag-over');
      });
      col.addEventListener('dragleave', () => col.classList.remove('drag-over'));
      col.addEventListener('drop', async (e) => {
        e.preventDefault();
        col.classList.remove('drag-over');
        const dragging = $('.task-card.dragging');
        if (!dragging) return;
        const id = dragging.dataset.id;
        const column = col.dataset.column;
        await fetchJson('/api/board/tasks/' + id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ column })
        });
        state.board = await fetchJson('/api/board');
        renderBoard();
        renderOverview();
      });
    });
  }

  function renderGit() {
    const { git } = state;
    if (!git) return;
    if (!git.isRepo) {
      $('#git-content').innerHTML = '<div class="empty-state">This folder is not a git repository (or git isn\\'t installed on this device).</div>';
      return;
    }

    const statusHtml = git.status.length
      ? git.status.map((s) => '<div class="status-row"><span class="status-state">' + escapeHtml(s.state) + '</span><span>' + escapeHtml(s.path) + '</span></div>').join('')
      : '<div class="empty-state">Working tree clean.</div>';

    const logHtml = git.log.length
      ? git.log.map((c) => (
          '<div class="commit-row">' +
          '<span class="commit-hash">' + escapeHtml(c.hash) + '</span>' +
          '<span class="commit-message">' + escapeHtml(c.message) + '</span>' +
          '<span class="commit-meta">' + escapeHtml(c.author) + ' · ' + escapeHtml(c.date) + '</span>' +
          '</div>'
        )).join('')
      : '<div class="empty-state">No commits yet.</div>';

    $('#git-content').innerHTML =
      '<span class="git-branch">on ' + escapeHtml(git.branch) + '</span>' +
      '<div class="git-section"><h3>Uncommitted changes (' + git.status.length + ')</h3>' + statusHtml + '</div>' +
      '<div class="git-section"><h3>Recent commits</h3>' + logHtml + '</div>';
  }

  function stopActiveRun() {
    if (state.activeRun) {
      state.activeRun.close();
      state.activeRun = null;
    }
  }

  function runScript(runnable, btn) {
    stopActiveRun();

    const consoleEl = $('#scripts-console');
    const output = $('#scripts-console-output');
    const title = $('#scripts-console-title');
    consoleEl.classList.remove('hidden');
    output.textContent = '';
    title.textContent = 'Running ' + runnable.name + '  (' + runnable.command + ')';

    $all('.script-run-btn').forEach((b) => (b.disabled = true));
    if (btn) btn.textContent = 'Running…';

    const es = new EventSource('/api/scripts/run?id=' + encodeURIComponent(runnable.id));
    state.activeRun = es;

    es.addEventListener('log', (e) => {
      const data = JSON.parse(e.data);
      output.textContent += data.text;
      output.scrollTop = output.scrollHeight;
    });

    const finish = (label) => {
      title.textContent = label;
      $all('.script-run-btn').forEach((b) => (b.disabled = false));
      es.close();
      if (state.activeRun === es) state.activeRun = null;
    };

    es.addEventListener('end', (e) => {
      const data = JSON.parse(e.data);
      finish(runnable.name + ' finished (exit code ' + data.code + ')');
    });

    es.onerror = () => finish(runnable.name + ' stopped');
  }

  function renderScripts() {
    const runnables = state.scripts;
    if (!runnables) return;
    if (!runnables.length) {
      $('#scripts-list').innerHTML = '<div class="empty-state">No .py files found next to this script yet. Add one, then reload.</div>';
      return;
    }
    $('#scripts-list').innerHTML = runnables
      .map((r, i) => (
        '<div class="script-item">' +
        '<span class="script-type">' + escapeHtml(r.type) + '</span>' +
        '<span class="script-name">' + escapeHtml(r.name) + '</span>' +
        '<span class="script-command">' + escapeHtml(r.command) + '</span>' +
        '<button class="script-run-btn" data-idx="' + i + '">Run</button>' +
        '</div>'
      ))
      .join('');

    $all('.script-run-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const runnable = runnables[Number(btn.dataset.idx)];
        runScript(runnable, btn);
      });
    });

    $('#scripts-console-stop').onclick = () => {
      stopActiveRun();
      $('#scripts-console-title').textContent = 'Stopped';
      $all('.script-run-btn').forEach((b) => (b.disabled = false));
    };
  }

  function renderHealth() {
    const health = state.health;
    if (!health) return;
    $('#health-content').innerHTML =
      '<div class="health-summary"><strong>' + health.passCount + ' / ' + health.total + '</strong> checks passing</div>' +
      health.checks
        .map((c) => (
          '<div class="health-check">' +
          '<span class="health-icon ' + c.status + '">' + (c.status === 'pass' ? '&#10003;' : c.status === 'warn' ? '!' : '&#10007;') + '</span>' +
          '<div class="health-body">' +
          '<div class="health-label">' + escapeHtml(c.label) + '</div>' +
          '<div class="health-detail">' + escapeHtml(c.detail) + '</div>' +
          '</div>' +
          '</div>'
        ))
        .join('');
  }

  let notesSaveTimer = null;

  function setupNotes(initialContent) {
    const editor = $('#notes-editor');
    editor.value = initialContent;
    const status = $('#notes-status');

    editor.addEventListener('input', () => {
      status.textContent = 'Saving…';
      clearTimeout(notesSaveTimer);
      notesSaveTimer = setTimeout(async () => {
        await fetch('/api/notes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: editor.value })
        });
        status.textContent = 'Saved to .codecompass/notes.md';
      }, 500);
    });
  }

  function setupPalette() {
    const overlay = $('#palette-overlay');
    const input = $('#palette-input');
    const results = $('#palette-results');
    let items = [];
    let activeIndex = 0;

    function buildItems(query) {
      const q = query.trim().toLowerCase();
      const tabItems = TAB_NAMES.map((name) => ({
        label: 'Go to ' + name[0].toUpperCase() + name.slice(1),
        hint: 'tab',
        action: () => switchTab(name)
      }));
      const scriptItems = (state.scripts || []).map((r) => ({
        label: 'Run ' + r.name,
        hint: r.type,
        action: () => {
          switchTab('scripts');
          runScript(r, null);
        }
      }));
      const all = tabItems.concat(scriptItems);
      if (!q) return all;
      return all.filter((it) => it.label.toLowerCase().indexOf(q) !== -1);
    }

    function render() {
      results.innerHTML = items
        .map((it, i) => (
          '<div class="palette-item' + (i === activeIndex ? ' active' : '') + '" data-idx="' + i + '">' +
          '<span class="palette-item-label">' + escapeHtml(it.label) + '</span>' +
          '<span class="palette-item-hint">' + escapeHtml(it.hint) + '</span>' +
          '</div>'
        ))
        .join('') || '<div class="empty-state">No matches.</div>';

      $all('.palette-item', results).forEach((el) => {
        el.addEventListener('click', () => {
          items[Number(el.dataset.idx)].action();
          close();
        });
      });
    }

    function open() {
      overlay.classList.remove('hidden');
      input.value = '';
      activeIndex = 0;
      items = buildItems('');
      render();
      input.focus();
    }

    function close() {
      overlay.classList.add('hidden');
    }

    input.addEventListener('input', () => {
      activeIndex = 0;
      items = buildItems(input.value);
      render();
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, items.length - 1);
        render();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        render();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (items[activeIndex]) {
          items[activeIndex].action();
          close();
        }
      } else if (e.key === 'Escape') {
        close();
      }
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });

    $('#palette-btn').addEventListener('click', open);

    document.addEventListener('keydown', (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        open();
        return;
      }
      if (e.key === 'Escape' && !overlay.classList.contains('hidden')) {
        close();
        return;
      }
      const tag = (document.activeElement && document.activeElement.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      const num = Number(e.key);
      if (num >= 1 && num <= TAB_NAMES.length) {
        switchTab(TAB_NAMES[num - 1]);
      }
    });
  }

  async function loadAll() {
    const [meta, scan, git, board, scripts, health, notes] = await Promise.all([
      fetchJson('/api/meta'),
      fetchJson('/api/scan'),
      fetchJson('/api/git'),
      fetchJson('/api/board'),
      fetchJson('/api/scripts'),
      fetchJson('/api/health'),
      fetchJson('/api/notes')
    ]);
    $('#project-path').textContent = meta.root;
    state.scan = scan;
    state.git = git;
    state.board = board;
    state.scripts = scripts;
    state.health = health;
    renderOverview();
    renderTodos();
    renderBoard();
    renderGit();
    renderScripts();
    renderHealth();
    setupNotes(notes.content);
    setupPalette();
  }

  function setupAddTaskForm() {
    $('#add-task-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = $('#new-task-title');
      const title = input.value.trim();
      if (!title) return;
      await fetchJson('/api/board/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, column: 'todo' })
      });
      input.value = '';
      state.board = await fetchJson('/api/board');
      renderBoard();
      renderOverview();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    setupAddTaskForm();
    loadAll().catch((err) => {
      console.error(err);
      $('#project-path').textContent = 'Failed to load project data — see console.';
    });
  });
})();
"""

FRONTEND_FILES = {
    '/': ('text/html; charset=utf-8', INDEX_HTML),
    '/index.html': ('text/html; charset=utf-8', INDEX_HTML),
    '/style.css': ('text/css; charset=utf-8', STYLE_CSS),
    '/app.js': ('application/javascript; charset=utf-8', APP_JS),
}


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
TASK_ROUTE_RE = re.compile(r'^/api/board/tasks/([^/]+)$')


class Handler(BaseHTTPRequestHandler):
    server_version = 'CodeCompass/1.0'

    def log_message(self, format_str, *args):
        pass

    def _send_json(self, status, data):
        body = json.dumps(data).encode('utf-8')
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        if length <= 0:
            return {}
        if length > 2_000_000:
            raise ValueError('Payload too large')
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8')) if raw else {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == '/api/meta':
                return self._send_json(200, {'root': PROJECT_ROOT})
            if path == '/api/scan':
                return self._send_json(200, scan_project(PROJECT_ROOT))
            if path == '/api/git':
                return self._send_json(200, get_git_info(PROJECT_ROOT))
            if path == '/api/board':
                return self._send_json(200, load_board(PROJECT_ROOT))
            if path == '/api/board/export':
                return self._handle_board_export()
            if path == '/api/notes':
                return self._send_json(200, {'content': get_notes(PROJECT_ROOT)})
            if path == '/api/health':
                return self._send_json(200, get_health(PROJECT_ROOT))
            if path == '/api/scripts':
                return self._send_json(200, list_runnables(PROJECT_ROOT))
            if path == '/api/scripts/run':
                run_id = (query.get('id') or [None])[0]
                return self._handle_script_run(run_id)

            if path in FRONTEND_FILES:
                content_type, body_str = FRONTEND_FILES[path]
                body = body_str.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not found')
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._send_json(500, {'error': str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == '/api/board/tasks':
                body = self._read_json_body()
                task = add_task(PROJECT_ROOT, body.get('title'), body.get('column', 'todo'), body.get('tag', ''), body.get('notes', ''))
                return self._send_json(201, task)
            if path == '/api/notes':
                body = self._read_json_body()
                save_notes(PROJECT_ROOT, body.get('content', ''))
                return self._send_json(200, {'saved': True})
            self.send_response(404)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._send_json(500, {'error': str(exc)})

    def do_PATCH(self):
        m = TASK_ROUTE_RE.match(urlparse(self.path).path)
        try:
            if m:
                body = self._read_json_body()
                task = update_task(PROJECT_ROOT, m.group(1), body)
                if not task:
                    return self._send_json(404, {'error': 'Task not found'})
                return self._send_json(200, task)
            self.send_response(404)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._send_json(500, {'error': str(exc)})

    def do_DELETE(self):
        m = TASK_ROUTE_RE.match(urlparse(self.path).path)
        try:
            if m:
                removed = delete_task(PROJECT_ROOT, m.group(1))
                return self._send_json(200 if removed else 404, {'removed': removed})
            self.send_response(404)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._send_json(500, {'error': str(exc)})

    def _handle_board_export(self):
        board = load_board(PROJECT_ROOT)
        sections = []
        for col in board['columns']:
            tasks = [t for t in board['tasks'] if t['column'] == col['id']]
            if tasks:
                lines = [
                    '- [{}] {}{}'.format(
                        'x' if col['id'] == 'done' else ' ',
                        t['title'],
                        '  _(' + t['tag'] + ')_' if t.get('tag') else ''
                    )
                    for t in tasks
                ]
            else:
                lines = ['_empty_']
            sections.append('## ' + col['title'] + '\n' + '\n'.join(lines))
        body = ('# Board export\n\n' + '\n\n'.join(sections) + '\n').encode('utf-8')
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/markdown; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="board.md"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_script_run(self, run_id):
        runnable = find_runnable(PROJECT_ROOT, run_id) if run_id else None
        if not runnable:
            return self._send_json(404, {'error': 'Unknown script'})

        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            return

        def send_event(event, data):
            payload = 'event: {}\ndata: {}\n\n'.format(event, json.dumps(data))
            self.wfile.write(payload.encode('utf-8'))
            self.wfile.flush()

        try:
            send_event('start', {'command': runnable['command']})
        except (BrokenPipeError, ConnectionResetError):
            return

        try:
            proc = start_runnable_process(PROJECT_ROOT, runnable)
        except OSError as exc:
            try:
                send_event('log', {'stream': 'stderr', 'text': 'Failed to start: ' + str(exc) + '\n'})
                send_event('end', {'code': None})
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        q = queue.Queue()

        def reader(pipe, tag):
            for line in iter(pipe.readline, ''):
                q.put((tag, line))
            pipe.close()

        t_out = threading.Thread(target=reader, args=(proc.stdout, 'stdout'), daemon=True)
        t_err = threading.Thread(target=reader, args=(proc.stderr, 'stderr'), daemon=True)
        t_out.start()
        t_err.start()

        def waiter():
            t_out.join()
            t_err.join()
            code = proc.wait()
            q.put(('__end__', code))

        threading.Thread(target=waiter, daemon=True).start()

        try:
            while True:
                tag, payload = q.get()
                if tag == '__end__':
                    send_event('end', {'code': payload})
                    break
                send_event('log', {'stream': tag, 'text': payload})
        except (BrokenPipeError, ConnectionResetError):
            if proc.poll() is None:
                proc.kill()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    os.makedirs(codecompass_dir(PROJECT_ROOT), exist_ok=True)

    try:
        server = Server(('127.0.0.1', PORT), Handler)
    except OSError as exc:
        print('Could not start on port {}: {}'.format(PORT, exc))
        print('Try setting a different port: set CODECOMPASS_PORT before running, e.g. 8001.')
        return

    url = 'http://127.0.0.1:{}'.format(PORT)
    print('')
    print('  CodeCompass is running:')
    print('  -> ' + url)
    print('')
    print('  Organizing: ' + PROJECT_ROOT)
    print('  Open the link above in your phone browser.')
    print('  Stop this script (Pydroid Stop button) to shut it down.')
    print('')

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
