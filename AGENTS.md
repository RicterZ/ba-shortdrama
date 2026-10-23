# Repository Layout

This is a single Git repository with one submodule. Setup, workflow, and
resource docs: `SETUP.md`, `WORKFLOW.md`, `RESOURCES.md`.

- Root repository: project documentation, `workspace.yaml`, `pyproject.toml`
  / `uv.lock`, and the production code in `code/ba-production`. Commit code
  changes here, not in a nested repo.
- `code/carocut` is a Git submodule of https://github.com/bilibili/carocut.
  Run `git submodule update --init` after cloning. Do not commit local carocut
  patches into the submodule pin without pushing them upstream.
- Dependencies are installed per checkout: `uv sync` (Python, root `.venv`)
  and `npm ci` in `code/ba-production`. Do not symlink `.venv`,
  `node_modules`, or the submodule from another checkout.
- `data`, `videos`, `attachments`, `local`, and `temp` under the repository
  root are not versioned. They live only in the primary checkout on the
  production machine; a fresh clone does not have them. Three kinds of files:
  - Resources (`data/`, `local/`, `temp/`: sprites, profiles, BGM, `.env`)
    are shared by every task and read from the asset root.
  - Episode output (`videos/<episode>/`: script, audio, renders) belongs to
    its episode but is always written to the primary checkout, so it survives
    branch switches and task worktrees and everyone sees the same copy.
  - Code is the only thing a worktree isolates; it goes through branches.
  Scripts find the primary checkout from git worktree metadata, so a task
  worktree needs no setup. Override with `BA_ASSETS_ROOT` / `.ba-assets-root`
  and `BA_OUTPUT_ROOT` (see `SETUP.md`). Do not symlink or copy these
  directories into a worktree, and do not leave output only in a worktree.
  Writers (`prepare`, `voice episode`, `render`) lock the episode, so a second
  task writing the same episode stops with an error instead of clobbering it.
- Never commit secrets from `local/.env`, downloaded media, caches, or dependencies.
