# Backlog Workflows

## Contents

- [Shared Rules](#shared-rules)
- [Create A UT Bug](#create-a-ut-bug)
- [Resolve A Bug](#resolve-a-bug)
- [Review Story And Task Deadlines](#review-story-and-task-deadlines)

## Shared Rules

- Use labels in commands and workflow config; resolve project-specific IDs from `config/projects/<PROJECT>.json`.
- Run `config audit-workflows` after changing workflow config, policy,
  guidance, output fields, or project catalogs.
- Refresh the project catalog before guessing a missing status, category, user, or custom-field option.
- Treat custom field values like `"Update Please"` (case-insensitive placeholder) as empty/unfilled when checking if a field is set.
- Run every mutation as a dry run first.
- Use the current local date for start-date rules.
- Set due date to start date plus two days where the workflow requires it.
- Do not invent issue content that is absent from the user request or issue context.

## Create A UT Bug

Run:

```bash
python3 scripts/backlog.py bug create-ut \
  PARENT_KEY \
  "MODULE" \
  "Issue description" \
  [--project KEY] \
  [--apply]
```

Apply the defaults from `config/workflows/ut_bug.json`:

- Set `QC Activity` to `Unit Test`.
- Resolve `Detected Role` as `Developer` from the project catalog.
- Assign the configured current user.
- Set status to `Closed`.
- Set start date to today and due date to two days later.
- Use the project-specific category override.
- Use one hour for estimated and actual hours unless configuration says otherwise.
- Build summary as `[Parent Ticket][Module] IssueDescription`.
- Set corrective action from the lowercased issue description.

Backlog does not accept `statusId` during issue creation. Create the issue first, then update it to `Closed`.

Preserve this description shape when details are available:

```markdown
**Environment**:

 **Pre-Condition**:
-

 **Steps to reproduce**:
1.
2.

**Actual**:

**Expected**:

 **Evidence**:
```

Leave unknown sections blank instead of fabricating content.

## Resolve A Bug

Get current rules and field guidance from the CLI:

```bash
python3 scripts/backlog.py bug rules
python3 scripts/backlog.py bug fields
python3 scripts/backlog.py bug fields <field>
```

Follow this sequence:

1. Run `bug context ISSUE_KEY`.
   Confirm `createdUser` is the intended QC/reporter assignee.
2. Inspect field guidance before choosing `qc_activity`, `bug_origin`, or `cause_category`.
3. Run `bug resolve ISSUE_KEY` without `--apply`.
4. Review `assignment`, `changes`, and `warnings`.
5. Apply only when the diff matches the request.

Use user-provided field values first. Infer a value only when the issue context and CLI guidance make it unambiguous; otherwise keep the configured default and disclose the uncertainty.

Pass `--fix-description` whenever possible. Without it, corrective action falls back to the cleaned issue summary and produces a warning.
Pass `--commit <hash-or-ref>` to append the implementation reference to the
Backlog comment. Add `--comment` when QC needs a concise verification note.

`bug fields` intentionally supports only selectable fields with documented
options: `qc_activity`, `bug_origin`, and `cause_category`. Inspect
`impacted`, `corrective_action`, and `resolution` in the resolve dry-run
instead of calling `bug fields` for them.

Resolve assigns to `createdUser` by workflow rule. If `Detected Role` is not
`Tester`, the dry-run warns that the reporter may not be the intended QC.

Do not resolve an issue merely because the user asked to inspect or analyze it.

## Review Story And Task Deadlines

Run:

```bash
python3 scripts/backlog.py story overview [--project KEY] [--query TEXT]
```

Include open Story and Task issues assigned to the configured current user. Report issue key, summary, description, status, due date, days remaining, and due alert.

Interpret alerts as:

- `dueAlertLevel = 1`: overdue.
- `dueAlertLevel = 2`: due today or tomorrow.
- `dueAlertLevel = null`: no alert or no due date.

Do not update Story or Task issues unless the user explicitly requests a mutation.
