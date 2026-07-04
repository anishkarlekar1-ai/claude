# CodeCompass for Android (Pydroid 3)

The main CodeCompass app (in the repo root) runs on Node.js, which isn't
available in Pydroid 3. This folder has a full rewrite in pure Python —
one single file, standard library only — so it runs directly inside Pydroid.

## Setup

1. Download `codecompass_android.py` onto your phone (e.g. from this repo,
   or however you received the file).
2. Move/copy it into the project folder you want to organize. It treats
   the folder it's sitting in as the project root.
3. Open it in Pydroid 3 and tap **Run**.
4. Pydroid's console will print a link like `http://127.0.0.1:8000` —
   open that in your phone's browser (Chrome, etc).
5. To stop the server, tap **Stop** in Pydroid.

If you'd rather not move the file into every project, set the
`CODECOMPASS_ROOT` environment variable... but Pydroid doesn't have an
easy way to set env vars per run, so the simplest approach is: keep one
copy of this script per project, right next to its code.

## What works differently from the Node version

- **Scripts tab**: lists any `.py` files sitting next to this script
  (instead of npm scripts/Makefile targets, since Android has neither).
  You can also define custom commands in a `codecompass_scripts.json`
  file in the same folder, e.g.:
  ```json
  { "say hi": "python hello.py" }
  ```
- **Git tab / health check**: most Android setups don't have a `git`
  binary installed. If it's missing, CodeCompass just shows "not a git
  repository" instead of crashing — everything else still works.
- Everything else (TODO scanner, language stats, kanban board, notes,
  health checklist, command palette) works exactly the same as the
  Node version.

## Port already in use?

Set a different port before running by editing the top of the file, or:
```
CODECOMPASS_PORT=8001 python codecompass_android.py
```
(if your version of Pydroid lets you set environment variables for a run;
otherwise just edit the `PORT = int(os.environ.get('CODECOMPASS_PORT', '8000'))`
line directly).
