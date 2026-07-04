(function () {
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
        card.dataset.dragging = 'true';
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
      $('#git-content').innerHTML = '<div class="empty-state">This directory is not a git repository.</div>';
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
      $('#scripts-list').innerHTML = '<div class="empty-state">No npm scripts or Makefile targets detected in this project.</div>';
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
