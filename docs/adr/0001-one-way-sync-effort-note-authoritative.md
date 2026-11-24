# Sync is one-way, and the Effort note is authoritative

Within the Personal repo, the Effort note is the authoritative record of an Effort, status included: its Effort folder sets the Intensity and whether the issue is open, done or canceled. Sync pushes Effort notes one way, from Obsidian to GitHub. The only thing that comes back is the Effort issue URL. GitHub is the published, queryable view (the Project board, the Inbox, search), not where status is set. We rejected two-way sync because two editable copies would need conflict resolution, and that cost outweighs the convenience of editing on GitHub.

## Consequences

- Sync owns the issue body between `<!-- obsidian:start -->` and `<!-- obsidian:end -->` (an Owned block). Edits there on GitHub get overwritten on the next run; discuss in comments instead.
- If you close or relabel an Effort issue on GitHub, the next Sync puts back whatever the Effort note says.
- Reversing this means redesigning the whole sync model.
