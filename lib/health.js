'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

function exists(root, relPath) {
  return fs.existsSync(path.join(root, relPath));
}

function anyExists(root, relPaths) {
  return relPaths.some((p) => exists(root, p));
}

function readJson(root, relPath) {
  try {
    return JSON.parse(fs.readFileSync(path.join(root, relPath), 'utf8'));
  } catch (e) {
    return null;
  }
}

function isGitRepo(root) {
  try {
    execFileSync('git', ['rev-parse', '--is-inside-work-tree'], { cwd: root, stdio: ['ignore', 'pipe', 'ignore'] });
    return true;
  } catch (e) {
    return false;
  }
}

function hasCommits(root) {
  try {
    execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, stdio: ['ignore', 'pipe', 'ignore'] });
    return true;
  } catch (e) {
    return false;
  }
}

function getHealth(root) {
  const checks = [];
  const pkg = readJson(root, 'package.json');

  checks.push({
    id: 'readme',
    label: 'README present',
    status: anyExists(root, ['README.md', 'README', 'readme.md']) ? 'pass' : 'fail',
    detail: 'A README helps anyone (including future you) understand the project quickly.'
  });

  checks.push({
    id: 'license',
    label: 'License present',
    status: anyExists(root, ['LICENSE', 'LICENSE.md', 'LICENSE.txt']) || (pkg && pkg.license) ? 'pass' : 'warn',
    detail: 'Clarifies how others are allowed to use the code.'
  });

  checks.push({
    id: 'gitignore',
    label: '.gitignore present',
    status: exists(root, '.gitignore') ? 'pass' : 'warn',
    detail: 'Keeps build artifacts and secrets out of version control.'
  });

  const git = isGitRepo(root);
  checks.push({
    id: 'git-repo',
    label: 'Git repository initialized',
    status: git ? 'pass' : 'fail',
    detail: 'Version control is the safety net for every other check here.'
  });

  if (git) {
    checks.push({
      id: 'git-commits',
      label: 'Has at least one commit',
      status: hasCommits(root) ? 'pass' : 'warn',
      detail: 'An empty repo means nothing is actually saved yet.'
    });
  }

  const ciPaths = ['.github/workflows', '.gitlab-ci.yml', '.circleci/config.yml', 'azure-pipelines.yml', '.travis.yml'];
  checks.push({
    id: 'ci',
    label: 'CI configuration present',
    status: anyExists(root, ciPaths) ? 'pass' : 'warn',
    detail: 'Automated checks catch regressions before they reach main.'
  });

  if (pkg) {
    const hasTestScript = pkg.scripts && pkg.scripts.test && !/no test specified/i.test(pkg.scripts.test);
    checks.push({
      id: 'test-script',
      label: 'package.json defines a test script',
      status: hasTestScript ? 'pass' : 'warn',
      detail: 'Lets contributors (and CI) run `npm test` without guessing.'
    });

    checks.push({
      id: 'pkg-description',
      label: 'package.json has a description',
      status: pkg.description ? 'pass' : 'warn',
      detail: 'Shows up on npm and in editor tooltips.'
    });

    const lockfiles = ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb'];
    checks.push({
      id: 'lockfile',
      label: 'Dependency lockfile present',
      status: anyExists(root, lockfiles) ? 'pass' : 'warn',
      detail: 'Pins exact dependency versions for reproducible installs.'
    });
  }

  const hasTestDir = anyExists(root, ['test', 'tests', '__tests__', 'spec']);
  checks.push({
    id: 'test-dir',
    label: 'Tests directory present',
    status: hasTestDir ? 'pass' : 'warn',
    detail: 'A dedicated place for tests keeps them discoverable.'
  });

  const passCount = checks.filter((c) => c.status === 'pass').length;
  return { checks, passCount, total: checks.length };
}

module.exports = { getHealth };
