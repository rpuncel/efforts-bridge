# Effort notes are matched to issues by full issue URL

After Sync creates an Effort issue, it writes the issue's full URL into the Effort note's frontmatter and uses that URL to match on every later run. We rejected matching by title, because renaming the note would orphan its issue; the full URL survives a rename. We also rejected matching by issue number, because the number alone doesn't name the repo. Every Synced effort carries this key, so changing it later means a migration across the whole vault.
