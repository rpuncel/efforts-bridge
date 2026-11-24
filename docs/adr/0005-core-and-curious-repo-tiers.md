# Repos are split into Core and Curious tiers

Core repos are watched for all activity. Curious repos are unwatched and read weekly through the Digest, which uses the API instead of notifications. Auto-watch of new repos is turned off, and repos the config doesn't list yet show up as Unsorted in the Digest's "please sort" list. We rejected watching everything and filtering, and curating by hand in GitHub's notification centre: both leave the notification feed as the place where attention gets decided.

This is the hardest decision to reverse. `cleanup --apply` unwatches repos in bulk and marks their notifications read, so the config is the only record of what used to be watched.
