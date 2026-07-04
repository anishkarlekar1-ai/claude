'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const MAKE_TARGET_RE = /^([A-Za-z0-9_.-]+)\s*:(?!=)/;
const IGNORED_TARGETS = new Set(['.PHONY', '.DEFAULT', '.SUFFIXES']);

function readJson(root, relPath) {
  try {
    return JSON.parse(fs.readFileSync(path.join(root, relPath), 'utf8'));
  } catch (e) {
    return null;
  }
}

function listNpmScripts(root) {
  const pkg = readJson(root, 'package.json');
  if (!pkg || !pkg.scripts) return [];
  return Object.keys(pkg.scripts).map((name) => ({
    type: 'npm',
    id: 'npm:' + name,
    name,
    command: pkg.scripts[name]
  }));
}

function listMakeTargets(root) {
  const makefilePath = ['Makefile', 'makefile'].map((f) => path.join(root, f)).find((f) => fs.existsSync(f));
  if (!makefilePath) return [];
  let content;
  try {
    content = fs.readFileSync(makefilePath, 'utf8');
  } catch (e) {
    return [];
  }
  const targets = [];
  const seen = new Set();
  content.split('\n').forEach((line) => {
    const match = MAKE_TARGET_RE.exec(line);
    if (!match) return;
    const name = match[1];
    if (IGNORED_TARGETS.has(name) || name.startsWith('.') || seen.has(name)) return;
    seen.add(name);
    targets.push({ type: 'make', id: 'make:' + name, name, command: 'make ' + name });
  });
  return targets;
}

function listRunnables(root) {
  return [...listNpmScripts(root), ...listMakeTargets(root)];
}

function findRunnable(root, id) {
  return listRunnables(root).find((r) => r.id === id) || null;
}

function runRunnable(root, runnable) {
  if (runnable.type === 'npm') {
    return spawn('npm', ['run', runnable.name], { cwd: root, shell: process.platform === 'win32' });
  }
  return spawn('make', [runnable.name], { cwd: root, shell: process.platform === 'win32' });
}

module.exports = { listRunnables, findRunnable, runRunnable };
