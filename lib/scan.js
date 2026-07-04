'use strict';

const fs = require('fs');
const path = require('path');

const IGNORED_DIRS = new Set([
  '.git', 'node_modules', 'dist', 'build', 'out', '.next', '.nuxt',
  'vendor', 'target', '.venv', 'venv', '__pycache__', 'coverage',
  '.codecompass', '.cache', '.parcel-cache'
]);

const LANGUAGES = {
  '.js': 'JavaScript', '.jsx': 'JavaScript', '.mjs': 'JavaScript', '.cjs': 'JavaScript',
  '.ts': 'TypeScript', '.tsx': 'TypeScript',
  '.py': 'Python', '.rb': 'Ruby', '.go': 'Go', '.rs': 'Rust',
  '.java': 'Java', '.kt': 'Kotlin', '.c': 'C', '.cc': 'C++', '.cpp': 'C++',
  '.h': 'C/C++ Header', '.hpp': 'C/C++ Header', '.cs': 'C#', '.php': 'PHP',
  '.swift': 'Swift', '.m': 'Objective-C', '.mm': 'Objective-C++', '.scala': 'Scala',
  '.sh': 'Shell', '.bash': 'Shell', '.md': 'Markdown', '.yml': 'YAML', '.yaml': 'YAML',
  '.json': 'JSON', '.html': 'HTML', '.css': 'CSS', '.scss': 'SCSS', '.vue': 'Vue',
  '.sql': 'SQL'
};

const TAG_RE = /\b(TODO|FIXME|HACK|XXX|BUG)\b:?\s*(.*)/;
const MAX_FILES = 6000;
const MAX_FILE_SIZE = 2 * 1024 * 1024; // 2MB
const NUL_BYTE = 0;

function isBinaryBuffer(buf) {
  const len = Math.min(buf.length, 512);
  for (let i = 0; i < len; i++) {
    if (buf[i] === NUL_BYTE) return true;
  }
  return false;
}

function walk(root, onFile, budget) {
  const stack = [root];
  while (stack.length && budget.count < MAX_FILES) {
    const dir = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (e) {
      continue;
    }
    for (const entry of entries) {
      if (entry.name.startsWith('.') && entry.isDirectory()) {
        if (!IGNORED_DIRS.has(entry.name)) continue;
      }
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (IGNORED_DIRS.has(entry.name)) continue;
        stack.push(full);
      } else if (entry.isFile()) {
        budget.count++;
        if (budget.count > MAX_FILES) return;
        onFile(full);
      }
    }
  }
}

function scanProject(root) {
  const byLanguage = new Map();
  const todos = [];
  let totalFiles = 0;
  let totalLines = 0;
  const budget = { count: 0 };

  walk(root, (filePath) => {
    const ext = path.extname(filePath).toLowerCase();
    const lang = LANGUAGES[ext];
    if (!lang) return;

    let stat;
    try {
      stat = fs.statSync(filePath);
    } catch (e) {
      return;
    }
    if (stat.size > MAX_FILE_SIZE) return;

    let buf;
    try {
      buf = fs.readFileSync(filePath);
    } catch (e) {
      return;
    }
    if (isBinaryBuffer(buf)) return;

    const content = buf.toString('utf8');
    const lines = content.split('\n');
    const lineCount = lines.length;

    totalFiles++;
    totalLines += lineCount;

    const entry = byLanguage.get(lang) || { language: lang, files: 0, lines: 0 };
    entry.files++;
    entry.lines += lineCount;
    byLanguage.set(lang, entry);

    const relPath = path.relative(root, filePath);
    for (let i = 0; i < lines.length; i++) {
      const match = TAG_RE.exec(lines[i]);
      if (match) {
        todos.push({
          file: relPath,
          line: i + 1,
          tag: match[1].toUpperCase(),
          text: match[2].trim().slice(0, 240)
        });
      }
    }
  }, budget);

  const languages = Array.from(byLanguage.values()).sort((a, b) => b.lines - a.lines);

  return {
    stats: {
      totalFiles,
      totalLines,
      languages,
      truncated: budget.count > MAX_FILES
    },
    todos
  };
}

module.exports = { scanProject };
