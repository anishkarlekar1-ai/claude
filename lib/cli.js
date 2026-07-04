'use strict';

const { scanProject } = require('./scan');
const { getGitInfo } = require('./git');
const { loadBoard, addTask, updateTask, deleteTask } = require('./board');
const { startServer } = require('./server');
const { getHealth } = require('./health');
const { listRunnables } = require('./scripts');

const HELP = `
CodeCompass - a project organizer for coders

Usage:
  codecompass                 Show a quick project summary
  codecompass scan            Print TODO/FIXME list and language stats
  codecompass serve [--port N]  Launch the web dashboard (default port 4321)
  codecompass health          Print a project health checklist
  codecompass scripts         List runnable npm scripts / Makefile targets
  codecompass task add <title> [--column todo|doing|done] [--tag TAG]
  codecompass task list
  codecompass task move <id> <column>
  codecompass task done <id>
  codecompass task rm <id>
  codecompass help
`;

function parseFlags(args) {
  const flags = {};
  const rest = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const next = args[i + 1];
      if (next !== undefined && !next.startsWith('--')) {
        flags[key] = next;
        i++;
      } else {
        flags[key] = true;
      }
    } else {
      rest.push(arg);
    }
  }
  return { flags, rest };
}

function printSummary(root) {
  const { stats, todos } = scanProject(root);
  const git = getGitInfo(root);
  const board = loadBoard(root);

  console.log('');
  console.log('CodeCompass summary for ' + root);
  console.log('-'.repeat(50));
  console.log('Files scanned: ' + stats.totalFiles + '   Lines: ' + stats.totalLines);
  if (stats.languages.length) {
    console.log('Top languages:');
    stats.languages.slice(0, 5).forEach((l) => {
      console.log('  ' + l.language.padEnd(16) + l.files + ' files, ' + l.lines + ' lines');
    });
  }
  console.log('Open TODO/FIXME markers: ' + todos.length);
  if (git.isRepo) {
    console.log('Git branch: ' + git.branch + '  (' + git.status.length + ' uncommitted changes)');
  } else {
    console.log('Git: not a repository');
  }
  const open = board.tasks.filter((t) => t.column !== 'done').length;
  console.log('Kanban tasks open: ' + open + ' / ' + board.tasks.length);
  console.log('-'.repeat(50));
  console.log("Run 'codecompass serve' to open the dashboard.");
  console.log('');
}

function printScan(root) {
  const { stats, todos } = scanProject(root);
  console.log('');
  console.log('Language breakdown:');
  stats.languages.forEach((l) => {
    console.log('  ' + l.language.padEnd(16) + l.files + ' files, ' + l.lines + ' lines');
  });
  console.log('');
  console.log('TODO/FIXME/HACK/XXX/BUG markers (' + todos.length + '):');
  todos.forEach((t) => {
    console.log('  [' + t.tag + '] ' + t.file + ':' + t.line + (t.text ? '  ' + t.text : ''));
  });
  console.log('');
}

function printHealth(root) {
  const { checks, passCount, total } = getHealth(root);
  console.log('');
  console.log('Project health: ' + passCount + '/' + total + ' checks passing');
  console.log('-'.repeat(50));
  const icon = { pass: '[x]', warn: '[!]', fail: '[ ]' };
  checks.forEach((c) => {
    console.log(' ' + icon[c.status] + ' ' + c.label);
  });
  console.log('');
}

function printScripts(root) {
  const runnables = listRunnables(root);
  console.log('');
  if (!runnables.length) {
    console.log('No npm scripts or Makefile targets found.');
    console.log('');
    return;
  }
  runnables.forEach((r) => {
    console.log('  ' + ('[' + r.type + ']').padEnd(8) + r.name.padEnd(20) + r.command);
  });
  console.log('');
}

function printBoard(root) {
  const board = loadBoard(root);
  console.log('');
  board.columns.forEach((col) => {
    const tasks = board.tasks.filter((t) => t.column === col.id);
    console.log(col.title + ' (' + tasks.length + ')');
    tasks.forEach((t) => {
      console.log('  [' + t.id + '] ' + t.title + (t.tag ? '  #' + t.tag : ''));
    });
    console.log('');
  });
}

function main(argv) {
  const root = process.cwd();
  const [command, ...args] = argv;

  if (!command) {
    return printSummary(root);
  }

  switch (command) {
    case 'help':
    case '--help':
    case '-h':
      console.log(HELP);
      return;

    case 'scan':
      return printScan(root);

    case 'health':
      return printHealth(root);

    case 'scripts':
      return printScripts(root);

    case 'serve': {
      const { flags } = parseFlags(args);
      const port = parseInt(flags.port, 10) || 4321;
      startServer(root, port);
      return;
    }

    case 'task': {
      const [sub, ...subArgs] = args;
      if (sub === 'add') {
        const { flags, rest } = parseFlags(subArgs);
        const title = rest.join(' ').trim();
        if (!title) {
          console.error('Usage: codecompass task add <title> [--column todo|doing|done] [--tag TAG]');
          process.exitCode = 1;
          return;
        }
        const task = addTask(root, { title, column: flags.column || 'todo', tag: flags.tag });
        console.log('Added task [' + task.id + '] ' + task.title);
        return;
      }
      if (sub === 'list') {
        return printBoard(root);
      }
      if (sub === 'move') {
        const [id, column] = subArgs;
        if (!id || !column) {
          console.error('Usage: codecompass task move <id> <column>');
          process.exitCode = 1;
          return;
        }
        const task = updateTask(root, id, { column });
        if (!task) {
          console.error('Task not found: ' + id);
          process.exitCode = 1;
          return;
        }
        console.log('Moved [' + task.id + '] to ' + task.column);
        return;
      }
      if (sub === 'done') {
        const [id] = subArgs;
        const task = updateTask(root, id, { column: 'done' });
        if (!task) {
          console.error('Task not found: ' + id);
          process.exitCode = 1;
          return;
        }
        console.log('Marked done: ' + task.title);
        return;
      }
      if (sub === 'rm') {
        const [id] = subArgs;
        const removed = deleteTask(root, id);
        console.log(removed ? 'Removed task ' + id : 'Task not found: ' + id);
        return;
      }
      console.log(HELP);
      return;
    }

    default:
      console.log(HELP);
      return;
  }
}

module.exports = { main };
