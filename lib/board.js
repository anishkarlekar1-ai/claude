'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_COLUMNS = [
  { id: 'todo', title: 'To Do' },
  { id: 'doing', title: 'In Progress' },
  { id: 'done', title: 'Done' }
];

function boardDir(root) {
  return path.join(root, '.codecompass');
}

function boardPath(root) {
  return path.join(boardDir(root), 'board.json');
}

function defaultBoard() {
  return { columns: DEFAULT_COLUMNS, tasks: [] };
}

function loadBoard(root) {
  const file = boardPath(root);
  if (!fs.existsSync(file)) return defaultBoard();
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (!parsed.columns) parsed.columns = DEFAULT_COLUMNS;
    if (!parsed.tasks) parsed.tasks = [];
    return parsed;
  } catch (e) {
    return defaultBoard();
  }
}

function saveBoard(root, board) {
  const dir = boardDir(root);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(boardPath(root), JSON.stringify(board, null, 2));
}

function makeId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function addTask(root, { title, column, notes, tag }) {
  const board = loadBoard(root);
  const validColumn = board.columns.some((c) => c.id === column) ? column : board.columns[0].id;
  const task = {
    id: makeId(),
    title: String(title || 'Untitled task').slice(0, 300),
    column: validColumn,
    notes: notes ? String(notes).slice(0, 2000) : '',
    tag: tag ? String(tag).slice(0, 100) : '',
    createdAt: new Date().toISOString()
  };
  board.tasks.push(task);
  saveBoard(root, board);
  return task;
}

function updateTask(root, id, fields) {
  const board = loadBoard(root);
  const task = board.tasks.find((t) => t.id === id);
  if (!task) return null;
  if (typeof fields.title === 'string') task.title = fields.title.slice(0, 300);
  if (typeof fields.notes === 'string') task.notes = fields.notes.slice(0, 2000);
  if (typeof fields.column === 'string' && board.columns.some((c) => c.id === fields.column)) {
    task.column = fields.column;
  }
  saveBoard(root, board);
  return task;
}

function deleteTask(root, id) {
  const board = loadBoard(root);
  const next = board.tasks.filter((t) => t.id !== id);
  const removed = next.length !== board.tasks.length;
  board.tasks = next;
  if (removed) saveBoard(root, board);
  return removed;
}

module.exports = { loadBoard, saveBoard, addTask, updateTask, deleteTask, boardPath };
