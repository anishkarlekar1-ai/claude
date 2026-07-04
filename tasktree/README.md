# TaskTree

A personal project/task planner for Pydroid 3 (or any device with Python 3):
create projects, nest subtasks inside subtasks as deep as you like, give any
task a due date and time, and see everything laid out on a calendar.

Single file, standard library only — no pip installs needed.

## Setup

1. Save `tasktree.py` anywhere on your phone (it doesn't need to sit inside
   any particular project folder — it keeps its own data file next to itself).
2. Open it in Pydroid 3 and tap **Run**.
3. Open the link it prints (e.g. `http://127.0.0.1:8010`) in your phone's browser.
4. Tap **Stop** in Pydroid to shut it down.

Your data is saved to `.tasktree/data.json` next to the script, so it
survives between runs.

## Using it

- **Projects tab**: create a project, tap it to open its task tree. "+ Add Task"
  adds a top-level task; "+ sub" on any task adds a subtask underneath it —
  nest as many levels deep as you want.
- Tap a task's title (or "edit") to change its title, notes, due date, or due
  time, or to delete it (deleting a task also deletes everything nested under it).
- The checkbox marks a task done. Overdue tasks (not done, past their due
  date/time) show a red badge; tasks due today show an amber badge.
- **Calendar tab**: a month view with a dot on every day that has something
  due. Tap a day to see exactly what's due, with a breadcrumb showing which
  project and parent task it belongs to.

## Notes

- If port 8010 is already in use, set a different one:
  `TASKTREE_PORT=8011 python tasktree.py` (if your Pydroid setup lets you set
  environment variables for a run), or just edit the `PORT = ...` line near
  the top of the file.
- This is a separate app from `android/codecompass_android.py` in this repo —
  that one scans an existing codebase for TODOs/health/etc; this one is a
  standalone personal planner with no connection to any particular codebase.
