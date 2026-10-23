# Worktree Resource Layout

This root repository tracks project documentation and workspace configuration.
The original resource directory is `/Users/sakana/Projects/ba-shortdrama`.

- `code/ba-production`, `code/carocut`, and `carocut` are independent Git
  repositories, not submodules. They are not copied into root worktrees.
- `data`, `videos`, `attachments`, `local`, and `temp` remain in the original
  resource directory. Use explicit paths when reading these shared resources.
- Never commit secrets from `local/.env`, downloaded media, caches, or dependencies.
- Do not assume relative resource paths in `workspace.yaml` resolve in a fresh
  worktree. Supply the original resource root explicitly where needed.
- Root worktree isolation does not isolate writes to the shared resources or
  nested repositories. Inspect them read-only unless the task requires edits;
  coordinate conflicting writes and use task-specific output directories.
- For source changes in a nested repository, use a separate worktree of that
  repository rather than concurrently editing its original working copy.
