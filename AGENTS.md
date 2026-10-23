# Repository Layout

This is a single Git repository with one submodule. The original resource
directory is `/Users/sakana/Projects/ba-shortdrama`.

- Root repository: project documentation, `workspace.yaml`, and the production
  code in `code/ba-production`. Commit code changes here, not in a nested repo.
- `code/carocut` is a Git submodule of https://github.com/bilibili/carocut.
  Run `git submodule update --init` in a fresh clone or worktree. Do not commit
  local carocut patches into the submodule pin without pushing them upstream.
- `data`, `videos`, `attachments`, `local`, and `temp` are local resources and
  are not versioned. They stay in the original resource directory; use explicit
  paths when reading them from a worktree.
- Never commit secrets from `local/.env`, downloaded media, caches, or dependencies.
- Worktree isolation does not isolate writes to the shared resources. Inspect
  them read-only unless the task requires edits, and use task-specific output
  directories.
