---
name: github-tickets
description: Use when a request names, links or asks you to choose a GitHub issue, and at each milestone of work for one (started, blocked, ready for review, merged). Picks the next issue from its project board, keeps the board Status and the issue comments current, and never closes, pushes or links an issue so that a merge closes it.
---

# GitHub tickets

Only the primary agent changes GitHub. Workers never run `gh` commands that change anything.
Project rules win: if they limit issue or board changes, make only what they allow and list the
rest, with the exact text you would have posted, in the final report.

## Look the issue up once

```sh
gh issue view N --repo OWNER/REPO --json number,title,state,body,labels,assignees,comments,url
gh api graphql -f owner=OWNER -f repo=REPO -F number=N -f query='
query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){
  projectItems(first:10){nodes{id
    project{id number title field(name:"Status"){... on ProjectV2SingleSelectField{id options{id name}}}}
    fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}'
```

Record the item, project, field and option IDs in `progress.md`. Never hard-code them: boards
differ. Map the options by meaning (Backlog or Todo, Ready, In progress, In review, Done). An issue
on no board gets comments only.

Set a status, then read it back with the query above:

```sh
gh project item-edit --id ITEM --project-id PROJECT --field-id FIELD --single-select-option-id OPTION
```

## Choosing what to work on

```sh
gh project item-list NUMBER --owner OWNER --limit 300 --format json --jq '.items[]
  | select(.content.type=="Issue" and .status!="Done")
  | {n:.content.number, title, status, priority, size, labels, assignees}'
```

Prefer Ready, then Backlog; higher Priority first, then the smaller Size, then the older issue.
Skip issues assigned to someone else, already In progress or In review, or waiting on another open
issue. An issue without acceptance criteria is not ready: say what is missing instead of
implementing a guess. If the user only asked which issue to take, answer with one line of
reasoning per candidate and change nothing.

## Keep the issue current

| Moment | Status | Comment |
|---|---|---|
| Work starts (after the first batch of questions) | In progress; `gh issue edit N --add-assignee @me` if unassigned | none |
| A decision the owner should see, or a blocker | unchanged | the decision and its reason, or the blocker and what unblocks it |
| Validated and waiting for the owner | In review | summary |
| The owner asked to merge; every acceptance criterion is met | Done; leave the issue open unless the owner asks to close it | merge commit, not pushed |
| A slice merged, work remains | In progress | what is done, what is left |

Post at most one comment per moment, with `gh issue comment N --repo OWNER/REPO --body-file -`.
A comment says, in a few lines: what changed for the user, the branch or commit, the checks run
with their counts, and what stays open (`Pending:`, `Unverified:`, `Manual:`), and whether anything
was pushed. No local paths, internal file names, logs or secrets.

## Never

- `Closes #N`, `Fixes #N` or `Resolves #N` in commits or pull requests: write `#N` or `Ref: #N`,
  so that no push or merge closes the issue.
- `gh issue develop` or a branch or pull request linked in the issue's Development section: merging
  that pull request closes the issue.
- Pushing, opening a pull request or closing an issue without the owner asking.

Report each change you made with its link: the status before and after, and the comment URL.
