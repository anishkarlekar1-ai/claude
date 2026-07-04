# CodeCompass

A zero-dependency CLI + local web dashboard that helps coders organize a project. Point it at any repo and get:

- **TODO/FIXME scanner** — finds `TODO`, `FIXME`, `HACK`, `XXX`, and `BUG` markers across your source tree, with file and line number.
- **Language & LOC stats** — file and line counts broken down by language.
- **Git activity view** — current branch, uncommitted changes, and recent commit history.
- **Kanban board** — a `To Do` / `In Progress` / `Done` board with drag-and-drop, persisted to `.codecompass/board.json` in the project you're organizing. One click turns any TODO marker into a board task. Export the board to Markdown for standups.
- **Script runner** — detects `package.json` scripts and `Makefile` targets and runs them with live streamed output, right in the dashboard.
- **Project health checklist** — README/LICENSE/.gitignore presence, git initialization, CI config, test script, lockfile, and more, each with a pass/warn/fail verdict.
- **Notes** — a per-project scratchpad (`.codecompass/notes.md`) that autosaves as you type.
- **Command palette** (`Ctrl`/`Cmd`+`K`) — jump to any tab or run any script without touching the mouse; number keys `1`–`7` also switch tabs directly.

No `npm install` required — it only uses Node's built-in modules.

## Usage

Run from the root of the project you want to organize:

```
node /path/to/codecompass/bin/codecompass.js            # quick summary
node /path/to/codecompass/bin/codecompass.js scan        # TODO list + language stats
node /path/to/codecompass/bin/codecompass.js health      # project health checklist
node /path/to/codecompass/bin/codecompass.js scripts     # list runnable npm scripts / Makefile targets
node /path/to/codecompass/bin/codecompass.js serve       # launch the dashboard (http://localhost:4321)
node /path/to/codecompass/bin/codecompass.js task add "Refactor auth module" --tag backend
node /path/to/codecompass/bin/codecompass.js task list
node /path/to/codecompass/bin/codecompass.js task move <id> doing
node /path/to/codecompass/bin/codecompass.js task done <id>
node /path/to/codecompass/bin/codecompass.js task rm <id>
```

Or install it globally / link it so `codecompass` is on your `PATH`:

```
npm link
codecompass serve
```

## Dashboard

`codecompass serve [--port 4321]` starts a local HTTP server with seven tabs:

- **Overview** — stat cards and a language breakdown chart.
- **TODOs** — every marker found in the codebase, each with a "+ Board" button to promote it to a kanban task.
- **Board** — drag cards between columns, add new tasks, remove finished ones, export the board as Markdown.
- **Scripts** — run any detected npm script or Makefile target and watch its stdout/stderr stream live.
- **Health** — a checklist of common project hygiene signals (README, LICENSE, CI, tests, lockfile, etc.).
- **Notes** — a free-form Markdown scratchpad that autosaves.
- **Git** — current branch, working tree status, and the last 20 commits.

Press `Ctrl`/`Cmd`+`K` anywhere to open the command palette, or the number keys `1`–`7` to jump straight to a tab.

All data is read live from the filesystem/git each time you load a tab — there's no build step or bundler.

## Project layout

```
bin/codecompass.js   CLI entry point
lib/cli.js           command parsing and terminal output
lib/scan.js          TODO scanner + language/LOC stats
lib/git.js           git branch/status/log via `git` CLI
lib/board.js         kanban board persistence (.codecompass/board.json)
lib/notes.js         notes scratchpad persistence (.codecompass/notes.md)
lib/health.js        project health checklist
lib/scripts.js       detects npm scripts / Makefile targets and runs them
lib/server.js        HTTP server + JSON API (including SSE script streaming) for the dashboard
public/              dashboard frontend (vanilla HTML/CSS/JS, no build step)
```

## Notes

- Scanned directories skip `node_modules`, `.git`, `dist`, `build`, `vendor`, `target`, virtualenvs, and similar generated/vendored folders.
- The kanban board and notes scratchpad are stored per-project in `.codecompass/` — add that path to your project's `.gitignore` if you don't want to commit it (or commit it if you want a shared team board/notes).
- The script runner executes `npm run <script>` or `make <target>` exactly as defined in your project — it doesn't run arbitrary commands, only what's already declared in `package.json` / `Makefile`.
