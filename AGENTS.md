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
- All tasks work in place in this checkout (`/Users/sakana/Projects/ba-shortdrama`
  on the production machine); do not create git worktrees for tasks.
- `data`, `videos`, `attachments`, `local`, and `temp` under the repository
  root are not versioned; a fresh clone does not have them.
  - Resources (`data/`, `local/`, `temp/`: sprites, profiles, BGM, `.env`)
    are shared by every task.
  - Episode output (`videos/<episode>/`: script, audio, renders) belongs to
    its episode and survives branch switches because it is outside git.
  Scripts read and write them under the repository root. Override with
  `BA_ASSETS_ROOT` / `.ba-assets-root` and `BA_OUTPUT_ROOT` (see `SETUP.md`).
  Writers (`prepare`, `voice episode`, `render`) lock the episode, so a second
  task writing the same episode stops with an error instead of clobbering it.
- Never commit secrets from `local/.env`, downloaded media, caches, or dependencies.
