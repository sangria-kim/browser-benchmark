# Agent work rules

These rules apply to all agents that work in this repository, including Podo and Codex.

## Branches

- Use `work/browser-benchmark` for repository changes.
- Use `main` as the owner-reviewed branch.
- Do not push changes directly to `main`.
- Do not merge a pull request into `main`. The repository owner performs that action.
- Keep the work branch after a merge. Reuse it for later work.
- Do not force-push, rewrite shared history, or delete shared branches.

## Before work

1. Read this file from `work/browser-benchmark`.
2. Fetch the latest remote refs.
3. Check for local changes. Preserve changes made by other contributors.
4. Update the local work branch from its remote branch with a fast-forward.
5. If `main` has commits missing from the work branch, merge `origin/main` into the work branch. Do not change `main`.
6. Inspect conflicts and concurrent edits before continuing. Do not overwrite another contributor's work.

## Delivery

1. Make only the changes needed for the task.
2. Validate the changed files before pushing. Check JSON syntax and local document links when relevant.
3. Fetch again before pushing. Integrate new work-branch commits and repeat affected checks.
4. Push to `work/browser-benchmark`.
5. Create or update a pull request from `work/browser-benchmark` to `main`.
6. State the changes, validation results, and known limits in the pull request.
7. Leave the pull request open for the owner. Do not enable automatic merge.

Use clear, short sentences in repository documents and pull requests. Follow ASD-STE100 principles where practical, at the requested approximate 80% level. Do not claim certified compliance.

## Public data boundary

Keep public browser feature information and source evidence in this repository.
Do not commit internal PRDs, private analysis, credentials, personal identifiers, or operation logs.
Follow `docs/collection-policy.md` and `docs/pm-persona-and-selection.md`.

## Consumers

A commit on `work/browser-benchmark` is an agent-validated candidate. It is not owner approval.
A consumer that tracks this branch can receive changes before a merge to `main`.
A consumer that tracks `main` receives changes only after the owner merges them.
Keep each consumer's selected source ref explicit. Record the imported commit SHA in the consumer environment.
These rules do not configure a downstream scheduler or change its source branch.
