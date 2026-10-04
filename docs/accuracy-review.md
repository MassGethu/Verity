# Accuracy review

The evidence validator previously required identical citation objects to associate a requirement or claim with a project, work entry or credential. A shorter exact quote was therefore incorrectly downgraded even when it appeared within a longer supporting quote. The fix accepts an excerpt only if its block ID matches and its quote is contained in the cited supporting passage. Matching IDs alone, disjoint assertions, invented text and joined lines do not qualify.

The same association rule now applies to requirement evidence, claim support and education evidence. If a match is downgraded because its passage is unsupported, its explanation describes the limited credit rather than retaining a contradictory strong-evidence rationale. Provider errors now display HTTP status and an allowlisted application validation reason without exposing provider responses, credentials or document content.

Seven new regression checks cover substring project support, different-block rejection, disjoint same-block rejection, claim support, invented/joined quote rejection, credential support, and detailed project evidence outranking repeated skills assertions and unrelated text. All 63 Django tests pass. This is a controlled regression suite, not an accuracy benchmark.

Live Maya reanalysis did not yield an accepted replacement in this session: a validation failure and a subsequent provider error left the previous saved result intact. Previously downgraded evidence cannot be recovered by revalidating the stored output, because the original provider evidence level was not retained. The displayed 70/100 result has not been manually raised. Valid fresh analysis is still needed to replace that saved result. No recruiter decision or guide edit was modified.

Public hosting is required for submission. Before deployment, select an account and storage option, configure a production server, secret key, allowed hosts, HTTPS, static assets and persistent database/media, and protect the recruiter workspace with judge access. Free ephemeral hosting must not be presented as durable SQLite/upload storage. Deployment and a live public URL have not yet been completed.
