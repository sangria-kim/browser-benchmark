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
7. For Codex delivery, run the `browser-benchmark-pr-review` skill after creating or updating the PR. The owner authorizes an independent review and a COMMENT review posted by `sangria-review-bot` for each new head commit. Read the skill from the local Codex skills directory. If it is unavailable, report the review step as pending.
8. Leave the pull request open for the owner. Do not enable automatic merge.

Use clear, short sentences in repository documents and pull requests. Follow ASD-STE100 principles where practical, at the requested approximate 80% level. Do not claim certified compliance.

## Collection scope

Collect browser updates from enabled entries in `config/sources.yml`. Classify each item using `docs/collection-policy.md`. Save only browser features and their official evidence. Keep all other candidates and operational files outside the repository.

Finish collection when the feature catalog and its evidence are validated. Internal transfer preparation, packaging, import, synchronization and downstream analysis belong to the consumer. Preserve existing historical records and links.
