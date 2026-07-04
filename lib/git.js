'use strict';

const { execFileSync } = require('child_process');

const UNIT_SEP = String.fromCharCode(31);

function run(root, args) {
  try {
    return execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch (e) {
    return null;
  }
}

function getGitInfo(root) {
  const inside = run(root, ['rev-parse', '--is-inside-work-tree']);
  if (inside !== 'true') {
    return { isRepo: false };
  }

  const branch = run(root, ['rev-parse', '--abbrev-ref', 'HEAD']) || 'HEAD';

  const statusRaw = run(root, ['status', '--porcelain']) || '';
  const status = statusRaw
    .split('\n')
    .filter(Boolean)
    .map((line) => ({ state: line.slice(0, 2).trim(), path: line.slice(3) }));

  const logRaw = run(root, ['log', '-20', '--pretty=format:%h' + UNIT_SEP + '%an' + UNIT_SEP + '%ar' + UNIT_SEP + '%s']) || '';
  const log = logRaw
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(UNIT_SEP);
      return { hash: parts[0], author: parts[1], date: parts[2], message: parts[3] };
    });

  return { isRepo: true, branch, status, log };
}

module.exports = { getGitInfo };
