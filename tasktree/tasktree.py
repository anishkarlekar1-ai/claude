#!/usr/bin/env python3
"""TaskTree - a nested project/task planner with a calendar, for Pydroid 3.

HOW TO USE
1. Save this file anywhere on your phone (it does not need to sit inside
   any particular project - it keeps its own data file next to itself).
2. Open it in Pydroid 3 and tap Run.
3. Open the link it prints (something like http://127.0.0.1:8010) in your
   phone's browser.
4. To stop it, go back to Pydroid and tap Stop.

Create projects, add tasks, nest subtasks inside subtasks as deep as you
like, give any task a due date and time, and use the Calendar tab to see
everything laid out by day. Data is stored in .tasktree/data.json next to
this file. Uses only the Python standard library - no pip installs needed.
"""

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '.tasktree')
DATA_FILE = os.path.join(DATA_DIR, 'data.json')
PORT = int(os.environ.get('TASKTREE_PORT', '8010'))

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TIME_RE = re.compile(r'^\d{2}:\d{2}$')


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def default_data():
    return {'projects': [], 'tasks': []}


def load_data():
    if not os.path.exists(DATA_FILE):
        return default_data()
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault('projects', [])
        data.setdefault('tasks', [])
        return data
    except (OSError, ValueError):
        return default_data()


def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def new_id():
    return format(int(time.time() * 1000), 'x') + format(int.from_bytes(os.urandom(4), 'big'), 'x')[:6]


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def clean_date(value):
    if isinstance(value, str) and DATE_RE.match(value):
        return value
    return None


def clean_time(value):
    if isinstance(value, str) and TIME_RE.match(value):
        return value
    return None


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def list_projects():
    data = load_data()
    result = []
    for p in data['projects']:
        tasks = [t for t in data['tasks'] if t['projectId'] == p['id']]
        result.append({
            'id': p['id'],
            'name': p['name'],
            'createdAt': p['createdAt'],
            'taskCount': len(tasks),
            'doneCount': sum(1 for t in tasks if t['done'])
        })
    return result


def create_project(name):
    data = load_data()
    project = {
        'id': new_id(),
        'name': str(name or 'Untitled project')[:200],
        'createdAt': now_iso()
    }
    data['projects'].append(project)
    save_data(data)
    return project


def delete_project(project_id):
    data = load_data()
    before = len(data['projects'])
    data['projects'] = [p for p in data['projects'] if p['id'] != project_id]
    removed = len(data['projects']) != before
    if removed:
        data['tasks'] = [t for t in data['tasks'] if t['projectId'] != project_id]
        save_data(data)
    return removed


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
def list_tasks_for_project(project_id):
    data = load_data()
    return [t for t in data['tasks'] if t['projectId'] == project_id]


def create_task(project_id, parent_id, title, notes, due_date, due_time):
    data = load_data()
    if not any(p['id'] == project_id for p in data['projects']):
        return None
    if parent_id and not any(t['id'] == parent_id and t['projectId'] == project_id for t in data['tasks']):
        parent_id = None
    task = {
        'id': new_id(),
        'projectId': project_id,
        'parentId': parent_id,
        'title': str(title or 'Untitled task')[:300],
        'notes': str(notes or '')[:4000],
        'done': False,
        'dueDate': clean_date(due_date),
        'dueTime': clean_time(due_time),
        'createdAt': now_iso()
    }
    data['tasks'].append(task)
    save_data(data)
    return task


def update_task(task_id, fields):
    data = load_data()
    task = next((t for t in data['tasks'] if t['id'] == task_id), None)
    if not task:
        return None
    if isinstance(fields.get('title'), str):
        task['title'] = fields['title'][:300]
    if isinstance(fields.get('notes'), str):
        task['notes'] = fields['notes'][:4000]
    if 'dueDate' in fields:
        task['dueDate'] = clean_date(fields['dueDate']) if fields['dueDate'] else None
    if 'dueTime' in fields:
        task['dueTime'] = clean_time(fields['dueTime']) if fields['dueTime'] else None
    if isinstance(fields.get('done'), bool):
        task['done'] = fields['done']
    save_data(data)
    return task


def _descendant_ids(tasks, root_id):
    ids = {root_id}
    changed = True
    while changed:
        changed = False
        for t in tasks:
            if t['parentId'] in ids and t['id'] not in ids:
                ids.add(t['id'])
                changed = True
    return ids


def delete_task(task_id):
    data = load_data()
    if not any(t['id'] == task_id for t in data['tasks']):
        return False
    doomed = _descendant_ids(data['tasks'], task_id)
    data['tasks'] = [t for t in data['tasks'] if t['id'] not in doomed]
    save_data(data)
    return True


def _breadcrumb(tasks_by_id, task):
    trail = []
    current = tasks_by_id.get(task['parentId'])
    while current:
        trail.append(current['title'])
        current = tasks_by_id.get(current['parentId'])
    trail.reverse()
    return trail


def list_due_tasks():
    data = load_data()
    projects_by_id = {p['id']: p for p in data['projects']}
    tasks_by_id = {t['id']: t for t in data['tasks']}
    result = []
    for t in data['tasks']:
        if not t['dueDate']:
            continue
        project = projects_by_id.get(t['projectId'])
        result.append({
            'id': t['id'],
            'projectId': t['projectId'],
            'projectName': project['name'] if project else 'Unknown project',
            'title': t['title'],
            'done': t['done'],
            'dueDate': t['dueDate'],
            'dueTime': t['dueTime'],
            'breadcrumb': _breadcrumb(tasks_by_id, t)
        })
    result.sort(key=lambda t: (t['dueDate'], t['dueTime'] or '99:99'))
    return result


# ---------------------------------------------------------------------------
# Frontend (embedded so this is a single downloadable file)
# ---------------------------------------------------------------------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>TaskTree</title>
<link rel="stylesheet" href="/style.css" />
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">&#127793;</span>
        <span class="brand-name">TaskTree</span>
      </div>
      <nav class="tabs" id="tabs">
        <button class="tab active" data-tab="projects">Projects</button>
        <button class="tab" data-tab="calendar">Calendar</button>
      </nav>
    </header>

    <main class="content">
      <section id="panel-projects" class="panel active">
        <div id="project-list-view">
          <div class="panel-head">
            <h2>Projects</h2>
            <button id="new-project-btn">+ New Project</button>
          </div>
          <div id="project-cards" class="project-cards"></div>
        </div>

        <div id="project-detail-view" class="hidden">
          <div class="panel-head">
            <button id="back-to-projects" class="back-btn">&larr; Projects</button>
            <h2 id="project-detail-title"></h2>
            <button id="add-top-task-btn">+ Add Task</button>
          </div>
          <div id="task-tree" class="task-tree"></div>
        </div>
      </section>

      <section id="panel-calendar" class="panel">
        <div class="panel-head">
          <button id="cal-prev" class="cal-nav-btn">&lsaquo;</button>
          <h2 id="cal-month-label"></h2>
          <button id="cal-next" class="cal-nav-btn">&rsaquo;</button>
        </div>
        <div id="calendar-grid" class="calendar-grid"></div>
        <div id="day-detail" class="day-detail hidden"></div>
      </section>
    </main>
  </div>

  <div id="task-modal-overlay" class="modal-overlay hidden">
    <div class="modal">
      <h3 id="task-modal-title">Add Task</h3>
      <form id="task-form">
        <input type="text" id="task-title-input" placeholder="Task title" required />
        <textarea id="task-notes-input" placeholder="Notes (optional)"></textarea>
        <div class="form-row">
          <label>Due date<input type="date" id="task-date-input" /></label>
          <label>Due time<input type="time" id="task-time-input" /></label>
        </div>
        <div class="modal-actions">
          <button type="button" id="task-delete-btn" class="danger hidden">Delete</button>
          <span class="spacer"></span>
          <button type="button" id="task-cancel-btn">Cancel</button>
          <button type="submit">Save</button>
        </div>
      </form>
    </div>
  </div>

  <div id="project-modal-overlay" class="modal-overlay hidden">
    <div class="modal">
      <h3>New Project</h3>
      <form id="project-form">
        <input type="text" id="project-name-input" placeholder="Project name" required />
        <div class="modal-actions">
          <span class="spacer"></span>
          <button type="button" id="project-cancel-btn">Cancel</button>
          <button type="submit">Create</button>
        </div>
      </form>
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
  padding: 14px 20px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 18px; }
.brand-mark { font-size: 22px; }

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
}
.tab:hover { background: var(--accent-soft); color: var(--text); }
.tab.active { background: var(--accent-soft); color: var(--accent); }

.content { padding: 20px; max-width: 900px; width: 100%; margin: 0 auto; flex: 1; }

.panel { display: none; }
.panel.active { display: block; }
.hidden { display: none !important; }

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.panel-head h2 { margin: 0; font-size: 18px; flex: 1; }

button {
  font-family: inherit;
  cursor: pointer;
}

#new-project-btn, #add-top-task-btn {
  background: var(--accent);
  border: none;
  color: #0f1117;
  font-weight: 600;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
}

.back-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
}
.back-btn:hover { border-color: var(--accent); color: var(--accent); }

.project-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}

.project-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  cursor: pointer;
}
.project-card:hover { border-color: var(--accent); }
.project-card .project-card-name { font-weight: 700; font-size: 15px; margin-bottom: 6px; }
.project-card .project-card-meta { color: var(--text-dim); font-size: 12.5px; }
.project-card .project-card-progress {
  margin-top: 10px;
  height: 6px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.project-card .project-card-progress-fill { height: 100%; background: var(--green); }
.project-card .project-card-delete {
  background: none; border: none; color: var(--text-dim); font-size: 11px; margin-top: 10px; padding: 0;
}
.project-card .project-card-delete:hover { color: var(--red); }

.empty-state { color: var(--text-dim); font-size: 14px; padding: 20px 0; }

.task-tree { display: flex; flex-direction: column; gap: 4px; }

.task-node { border-left: 2px solid transparent; }
.task-node.depth-parent { border-left-color: var(--border); }

.task-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  margin-bottom: 4px;
  font-size: 13.5px;
  flex-wrap: wrap;
}
.task-row:hover { border-color: var(--accent); }

.task-checkbox { margin-top: 3px; flex-shrink: 0; width: 16px; height: 16px; }

.task-main { flex: 1; min-width: 120px; }
.task-title-text { cursor: pointer; }
.task-title-text.done { text-decoration: line-through; color: var(--text-dim); }
.task-due-badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  margin-top: 4px;
  background: var(--accent-soft);
  color: var(--accent);
}
.task-due-badge.overdue { background: rgba(242, 119, 122, 0.15); color: var(--red); }
.task-due-badge.due-today { background: rgba(242, 193, 78, 0.15); color: var(--amber); }

.task-actions { display: flex; gap: 6px; flex-shrink: 0; }
.task-actions button {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 6px;
  padding: 3px 9px;
  font-size: 11.5px;
}
.task-actions button:hover { border-color: var(--accent); color: var(--accent); }
.task-actions button.task-del-btn:hover { border-color: var(--red); color: var(--red); }

.task-children { margin-left: 22px; margin-top: 4px; }

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
  margin-bottom: 16px;
}

.cal-weekday { text-align: center; font-size: 11px; color: var(--text-dim); padding: 4px 0; font-weight: 600; }

.cal-day {
  aspect-ratio: 1 / 1;
  min-height: 44px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  padding: 4px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  font-size: 11px;
  color: var(--text);
  overflow: hidden;
}
.cal-day:hover { border-color: var(--accent); }
.cal-day.empty { visibility: hidden; }
.cal-day.today { border-color: var(--accent); border-width: 2px; }
.cal-day.selected { background: var(--accent-soft); }
.cal-day-num { font-weight: 600; }
.cal-day-dot-row { display: flex; gap: 2px; margin-top: auto; flex-wrap: wrap; }
.cal-day-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.cal-day-dot.overdue { background: var(--red); }
.cal-day-dot.done { background: var(--green); }

.cal-nav-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 8px;
  width: 34px;
  height: 34px;
  font-size: 16px;
}
.cal-nav-btn:hover { border-color: var(--accent); }

.day-detail {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.day-detail h3 { margin: 0 0 10px; font-size: 15px; }

.day-task-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.day-task-row:last-child { border-bottom: none; }
.day-task-main { flex: 1; }
.day-task-breadcrumb { color: var(--text-dim); font-size: 11px; margin-top: 2px; }
.day-task-time { color: var(--text-dim); font-size: 11px; flex-shrink: 0; }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(10, 12, 18, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 100;
}

.modal {
  width: min(420px, 100%);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.modal h3 { margin: 0 0 14px; font-size: 16px; }

.modal input[type="text"], .modal textarea {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  color: var(--text);
  font-size: 14px;
  margin-bottom: 10px;
  font-family: inherit;
}
.modal textarea { min-height: 70px; resize: vertical; }

.form-row { display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.form-row label { flex: 1; font-size: 12px; color: var(--text-dim); min-width: 130px; }
.form-row input {
  display: block;
  width: 100%;
  margin-top: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  color: var(--text);
  font-size: 13px;
}

.modal-actions { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.modal-actions .spacer { flex: 1; }
.modal-actions button {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
}
.modal-actions button[type="submit"] { background: var(--accent); color: #0f1117; border: none; font-weight: 600; }
.modal-actions button.danger { border-color: var(--red); color: var(--red); background: transparent; }
"""

APP_JS = """(function () {
  'use strict';

  const state = {
    projects: [],
    currentProjectId: null,
    tasks: [],
    dueTasks: [],
    calYear: new Date().getFullYear(),
    calMonth: new Date().getMonth(),
    selectedDate: null,
    modalMode: null,
    modalContext: null
  };

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

  function todayStr() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function nowTimeStr() {
    const d = new Date();
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  function dueStatus(task) {
    if (!task.dueDate || task.done) return 'none';
    const today = todayStr();
    if (task.dueDate < today) return 'overdue';
    if (task.dueDate === today) {
      if (task.dueTime && task.dueTime < nowTimeStr()) return 'overdue';
      return 'due-today';
    }
    return 'upcoming';
  }

  function formatDue(task) {
    if (!task.dueDate) return '';
    let text = task.dueDate;
    if (task.dueTime) text += ' ' + task.dueTime;
    return text;
  }

  // ---------------- Tabs ----------------
  function switchTab(name) {
    $all('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
    $all('.panel').forEach((p) => p.classList.toggle('active', p.id === 'panel-' + name));
    if (name === 'calendar') {
      loadCalendar();
    }
  }

  function setupTabs() {
    $all('.tab').forEach((tab) => tab.addEventListener('click', () => switchTab(tab.dataset.tab)));
  }

  // ---------------- Projects ----------------
  async function loadProjects() {
    state.projects = await fetchJson('/api/projects');
    renderProjectCards();
  }

  function renderProjectCards() {
    const container = $('#project-cards');
    if (!state.projects.length) {
      container.innerHTML = '<div class="empty-state">No projects yet. Tap "+ New Project" to start one.</div>';
      return;
    }
    container.innerHTML = state.projects
      .map((p) => {
        const pct = p.taskCount ? Math.round((p.doneCount / p.taskCount) * 100) : 0;
        return (
          '<div class="project-card" data-id="' + p.id + '">' +
          '<div class="project-card-name">' + escapeHtml(p.name) + '</div>' +
          '<div class="project-card-meta">' + p.doneCount + ' / ' + p.taskCount + ' tasks done</div>' +
          '<div class="project-card-progress"><div class="project-card-progress-fill" style="width:' + pct + '%"></div></div>' +
          '<button class="project-card-delete" data-id="' + p.id + '">Delete project</button>' +
          '</div>'
        );
      })
      .join('');

    $all('.project-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.classList.contains('project-card-delete')) return;
        openProject(card.dataset.id);
      });
    });
    $all('.project-card-delete').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm('Delete this project and all its tasks?')) return;
        await fetch('/api/projects/' + btn.dataset.id, { method: 'DELETE' });
        await loadProjects();
      });
    });
  }

  async function openProject(projectId) {
    state.currentProjectId = projectId;
    const project = state.projects.find((p) => p.id === projectId);
    $('#project-detail-title').textContent = project ? project.name : '';
    $('#project-list-view').classList.add('hidden');
    $('#project-detail-view').classList.remove('hidden');
    await loadTasks();
  }

  function backToProjects() {
    state.currentProjectId = null;
    $('#project-detail-view').classList.add('hidden');
    $('#project-list-view').classList.remove('hidden');
    loadProjects();
  }

  async function loadTasks() {
    state.tasks = await fetchJson('/api/projects/' + state.currentProjectId + '/tasks');
    renderTaskTree();
  }

  function buildTree(tasks) {
    const byId = {};
    tasks.forEach((t) => (byId[t.id] = Object.assign({}, t, { children: [] })));
    const roots = [];
    tasks.forEach((t) => {
      if (t.parentId && byId[t.parentId]) byId[t.parentId].children.push(byId[t.id]);
      else roots.push(byId[t.id]);
    });
    const sortFn = (a, b) => (a.createdAt < b.createdAt ? -1 : 1);
    const sortRec = (list) => {
      list.sort(sortFn);
      list.forEach((n) => sortRec(n.children));
    };
    sortRec(roots);
    return roots;
  }

  function renderTaskNode(task, depth) {
    const status = dueStatus(task);
    const badgeClass = status === 'overdue' ? 'overdue' : status === 'due-today' ? 'due-today' : '';
    const dueHtml = task.dueDate
      ? '<div class="task-due-badge ' + badgeClass + '">' + escapeHtml(formatDue(task)) + '</div>'
      : '';
    const childrenHtml = task.children.length
      ? '<div class="task-children">' + task.children.map((c) => renderTaskNode(c, depth + 1)).join('') + '</div>'
      : '';
    return (
      '<div class="task-node' + (depth > 0 ? ' depth-parent' : '') + '">' +
      '<div class="task-row" data-id="' + task.id + '">' +
      '<input type="checkbox" class="task-checkbox" data-id="' + task.id + '"' + (task.done ? ' checked' : '') + ' />' +
      '<div class="task-main">' +
      '<span class="task-title-text' + (task.done ? ' done' : '') + '" data-id="' + task.id + '">' + escapeHtml(task.title) + '</span>' +
      dueHtml +
      '</div>' +
      '<div class="task-actions">' +
      '<button class="task-add-sub-btn" data-id="' + task.id + '">+ sub</button>' +
      '<button class="task-edit-btn" data-id="' + task.id + '">edit</button>' +
      '<button class="task-del-btn" data-id="' + task.id + '">delete</button>' +
      '</div>' +
      '</div>' +
      childrenHtml +
      '</div>'
    );
  }

  function renderTaskTree() {
    const tree = buildTree(state.tasks);
    const container = $('#task-tree');
    if (!tree.length) {
      container.innerHTML = '<div class="empty-state">No tasks yet. Tap "+ Add Task" to create one.</div>';
      return;
    }
    container.innerHTML = tree.map((t) => renderTaskNode(t, 0)).join('');

    $all('.task-checkbox', container).forEach((cb) => {
      cb.addEventListener('change', async () => {
        await fetchJson('/api/tasks/' + cb.dataset.id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ done: cb.checked })
        });
        await loadTasks();
      });
    });
    $all('.task-title-text', container).forEach((el) => {
      el.addEventListener('click', () => openEditTaskModal(el.dataset.id));
    });
    $all('.task-edit-btn', container).forEach((btn) => {
      btn.addEventListener('click', () => openEditTaskModal(btn.dataset.id));
    });
    $all('.task-add-sub-btn', container).forEach((btn) => {
      btn.addEventListener('click', () => openCreateTaskModal(state.currentProjectId, btn.dataset.id));
    });
    $all('.task-del-btn', container).forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this task and any subtasks under it?')) return;
        await fetch('/api/tasks/' + btn.dataset.id, { method: 'DELETE' });
        await loadTasks();
      });
    });
  }

  // ---------------- Task modal ----------------
  function openCreateTaskModal(projectId, parentId) {
    state.modalMode = 'create';
    state.modalContext = { projectId, parentId };
    $('#task-modal-title').textContent = parentId ? 'Add Subtask' : 'Add Task';
    $('#task-title-input').value = '';
    $('#task-notes-input').value = '';
    $('#task-date-input').value = '';
    $('#task-time-input').value = '';
    $('#task-delete-btn').classList.add('hidden');
    $('#task-modal-overlay').classList.remove('hidden');
    $('#task-title-input').focus();
  }

  function openEditTaskModal(taskId) {
    const task = state.tasks.find((t) => t.id === taskId);
    if (!task) return;
    state.modalMode = 'edit';
    state.modalContext = { taskId };
    $('#task-modal-title').textContent = 'Edit Task';
    $('#task-title-input').value = task.title;
    $('#task-notes-input').value = task.notes || '';
    $('#task-date-input').value = task.dueDate || '';
    $('#task-time-input').value = task.dueTime || '';
    $('#task-delete-btn').classList.remove('hidden');
    $('#task-modal-overlay').classList.remove('hidden');
    $('#task-title-input').focus();
  }

  function closeTaskModal() {
    $('#task-modal-overlay').classList.add('hidden');
  }

  function setupTaskModal() {
    $('#task-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        title: $('#task-title-input').value.trim(),
        notes: $('#task-notes-input').value,
        dueDate: $('#task-date-input').value || null,
        dueTime: $('#task-time-input').value || null
      };
      if (!payload.title) return;

      if (state.modalMode === 'create') {
        payload.projectId = state.modalContext.projectId;
        payload.parentId = state.modalContext.parentId;
        await fetchJson('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        await fetchJson('/api/tasks/' + state.modalContext.taskId, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }
      closeTaskModal();
      await loadTasks();
    });

    $('#task-cancel-btn').addEventListener('click', closeTaskModal);
    $('#task-delete-btn').addEventListener('click', async () => {
      if (!confirm('Delete this task and any subtasks under it?')) return;
      await fetch('/api/tasks/' + state.modalContext.taskId, { method: 'DELETE' });
      closeTaskModal();
      await loadTasks();
    });
    $('#task-modal-overlay').addEventListener('click', (e) => {
      if (e.target.id === 'task-modal-overlay') closeTaskModal();
    });
  }

  // ---------------- Project modal ----------------
  function setupProjectModal() {
    $('#new-project-btn').addEventListener('click', () => {
      $('#project-name-input').value = '';
      $('#project-modal-overlay').classList.remove('hidden');
      $('#project-name-input').focus();
    });
    $('#project-cancel-btn').addEventListener('click', () => {
      $('#project-modal-overlay').classList.add('hidden');
    });
    $('#project-modal-overlay').addEventListener('click', (e) => {
      if (e.target.id === 'project-modal-overlay') $('#project-modal-overlay').classList.add('hidden');
    });
    $('#project-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = $('#project-name-input').value.trim();
      if (!name) return;
      await fetchJson('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      $('#project-modal-overlay').classList.add('hidden');
      await loadProjects();
    });
  }

  // ---------------- Calendar ----------------
  const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  async function loadCalendar() {
    state.dueTasks = await fetchJson('/api/tasks/due');
    renderCalendar();
  }

  function renderCalendar() {
    const year = state.calYear;
    const month = state.calMonth;
    $('#cal-month-label').textContent = MONTH_NAMES[month] + ' ' + year;

    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = todayStr();

    const tasksByDate = {};
    state.dueTasks.forEach((t) => {
      (tasksByDate[t.dueDate] = tasksByDate[t.dueDate] || []).push(t);
    });

    let cells = WEEKDAYS.map((w) => '<div class="cal-weekday">' + w + '</div>').join('');

    for (let i = 0; i < firstDay; i++) {
      cells += '<div class="cal-day empty"></div>';
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
      const dayTasks = tasksByDate[dateStr] || [];
      const isToday = dateStr === today;
      const isSelected = dateStr === state.selectedDate;
      const dots = dayTasks
        .slice(0, 6)
        .map((t) => {
          let cls = 'cal-day-dot';
          if (t.done) cls += ' done';
          else if (dueStatusFromDate(t, today) === 'overdue') cls += ' overdue';
          return '<span class="' + cls + '"></span>';
        })
        .join('');
      cells +=
        '<div class="cal-day' + (isToday ? ' today' : '') + (isSelected ? ' selected' : '') + '" data-date="' + dateStr + '">' +
        '<span class="cal-day-num">' + day + '</span>' +
        '<div class="cal-day-dot-row">' + dots + '</div>' +
        '</div>';
    }

    $('#calendar-grid').innerHTML = cells;

    $all('.cal-day:not(.empty)').forEach((el) => {
      el.addEventListener('click', () => selectDay(el.dataset.date));
    });

    if (state.selectedDate) {
      renderDayDetail(state.selectedDate);
    }
  }

  function dueStatusFromDate(task, today) {
    if (task.done) return 'done';
    if (task.dueDate < today) return 'overdue';
    return 'upcoming';
  }

  function selectDay(dateStr) {
    state.selectedDate = dateStr;
    renderCalendar();
    renderDayDetail(dateStr);
  }

  function renderDayDetail(dateStr) {
    const panel = $('#day-detail');
    const dayTasks = state.dueTasks.filter((t) => t.dueDate === dateStr);
    panel.classList.remove('hidden');
    if (!dayTasks.length) {
      panel.innerHTML = '<h3>' + dateStr + '</h3><div class="empty-state">Nothing due this day.</div>';
      return;
    }
    panel.innerHTML =
      '<h3>' + dateStr + '</h3>' +
      dayTasks
        .map((t) => {
          const crumb = [t.projectName].concat(t.breadcrumb).join(' / ');
          return (
            '<div class="day-task-row">' +
            '<input type="checkbox" class="day-task-checkbox" data-id="' + t.id + '"' + (t.done ? ' checked' : '') + ' />' +
            '<div class="day-task-main">' +
            '<div class="' + (t.done ? 'done' : '') + '">' + escapeHtml(t.title) + '</div>' +
            '<div class="day-task-breadcrumb">' + escapeHtml(crumb) + '</div>' +
            '</div>' +
            '<div class="day-task-time">' + escapeHtml(t.dueTime || '') + '</div>' +
            '</div>'
          );
        })
        .join('');

    $all('.day-task-checkbox', panel).forEach((cb) => {
      cb.addEventListener('change', async () => {
        await fetchJson('/api/tasks/' + cb.dataset.id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ done: cb.checked })
        });
        await loadCalendar();
      });
    });
  }

  function setupCalendarNav() {
    $('#cal-prev').addEventListener('click', () => {
      state.calMonth -= 1;
      if (state.calMonth < 0) {
        state.calMonth = 11;
        state.calYear -= 1;
      }
      renderCalendar();
    });
    $('#cal-next').addEventListener('click', () => {
      state.calMonth += 1;
      if (state.calMonth > 11) {
        state.calMonth = 0;
        state.calYear += 1;
      }
      renderCalendar();
    });
  }

  // ---------------- Init ----------------
  document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    setupProjectModal();
    setupTaskModal();
    setupCalendarNav();
    $('#back-to-projects').addEventListener('click', backToProjects);
    $('#add-top-task-btn').addEventListener('click', () => openCreateTaskModal(state.currentProjectId, null));
    loadProjects();
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
PROJECT_TASKS_RE = re.compile(r'^/api/projects/([^/]+)/tasks$')
PROJECT_RE = re.compile(r'^/api/projects/([^/]+)$')
TASK_RE = re.compile(r'^/api/tasks/([^/]+)$')


class Handler(BaseHTTPRequestHandler):
    server_version = 'TaskTree/1.0'

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
        path = urlparse(self.path).path
        try:
            if path == '/api/projects':
                return self._send_json(200, list_projects())
            if path == '/api/tasks/due':
                return self._send_json(200, list_due_tasks())

            m = PROJECT_TASKS_RE.match(path)
            if m:
                return self._send_json(200, list_tasks_for_project(m.group(1)))

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
            if path == '/api/projects':
                body = self._read_json_body()
                project = create_project(body.get('name'))
                return self._send_json(201, project)
            if path == '/api/tasks':
                body = self._read_json_body()
                task = create_task(
                    body.get('projectId'), body.get('parentId'), body.get('title'),
                    body.get('notes'), body.get('dueDate'), body.get('dueTime')
                )
                if not task:
                    return self._send_json(400, {'error': 'Unknown project'})
                return self._send_json(201, task)
            self.send_response(404)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self._send_json(500, {'error': str(exc)})

    def do_PATCH(self):
        path = urlparse(self.path).path
        m = TASK_RE.match(path)
        try:
            if m:
                body = self._read_json_body()
                task = update_task(m.group(1), body)
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
        path = urlparse(self.path).path
        m = TASK_RE.match(path)
        if m:
            try:
                removed = delete_task(m.group(1))
                return self._send_json(200 if removed else 404, {'removed': removed})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                return self._send_json(500, {'error': str(exc)})

        m = PROJECT_RE.match(path)
        if m:
            try:
                removed = delete_project(m.group(1))
                return self._send_json(200 if removed else 404, {'removed': removed})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                return self._send_json(500, {'error': str(exc)})

        self.send_response(404)
        self.end_headers()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        server = Server(('127.0.0.1', PORT), Handler)
    except OSError as exc:
        print('Could not start on port {}: {}'.format(PORT, exc))
        print('Try setting a different port: set TASKTREE_PORT before running, e.g. 8011.')
        return

    url = 'http://127.0.0.1:{}'.format(PORT)
    print('')
    print('  TaskTree is running:')
    print('  -> ' + url)
    print('')
    print('  Data file: ' + DATA_FILE)
    print('  Open the link above in your phone browser.')
    print('  Stop this script (Pydroid Stop button) to shut it down.')
    print('')

    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
