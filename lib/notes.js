'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_NOTES = '# Project Notes\n\nJot down decisions, context for future-you, or anything worth remembering.\n';

function notesDir(root) {
  return path.join(root, '.codecompass');
}

function notesPath(root) {
  return path.join(notesDir(root), 'notes.md');
}

function getNotes(root) {
  const file = notesPath(root);
  if (!fs.existsSync(file)) return DEFAULT_NOTES;
  try {
    return fs.readFileSync(file, 'utf8');
  } catch (e) {
    return DEFAULT_NOTES;
  }
}

function saveNotes(root, content) {
  const dir = notesDir(root);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(notesPath(root), String(content).slice(0, 200000));
}

module.exports = { getNotes, saveNotes };
