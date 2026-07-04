(function () {
  'use strict';

  const state = {
    scan: null,
    git: null,
    board: null
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

  function setupTabs() {
    $all('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        $all('.tab').forEach((t) => t.classList.remove('active'));
        $all('.panel').forEach((p) => p.classList.remove('active'));
        tab.classList.add('active');
        $('#panel-' + tab.dataset.tab).classList.add('active');
      });
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

  async function loadAll() {
    const [meta, scan, git, board] = await Promise.all([
      fetchJson('/api/meta'),
      fetchJson('/api/scan'),
      fetchJson('/api/git'),
      fetchJson('/api/board')
    ]);
    $('#project-path').textContent = meta.root;
    state.scan = scan;
    state.git = git;
    state.board = board;
    renderOverview();
    renderTodos();
    renderBoard();
    renderGit();
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
