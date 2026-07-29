# Repository hygiene

The source repository contains code, documentation, schemas, sanitized
fixtures, public exact-list card metadata, and redacted protocol examples.

It must not contain:

- `run/` or complete Game Record directories
- checkpoints, initial checkpoints, library order, or opposing hidden zones
- live capability values or provider credentials
- pilot memory or private decision packets
- SQLite databases, Scryfall bulk downloads, or Moxfield caches
- build outputs, wheels, locks, logs, or local virtual environments

`scripts/validate_repository.py` checks tracked files and reachable Git history
for these path classes, common secret forms, raw capability literals, and
oversized blobs. CI rebuilds its small SQLite database from
`tests/fixtures/scryfall-exact-lists.json`.

## Pre-publication history rewrite

Before the first remote was created, the sole local history was backed up and
rewritten because earlier commits tracked local `run/` and `demo/` artifacts,
including bearer capabilities. The unapproved historical license file was also
removed. The original local root was
`dfe5a19c1fe08f0c4dc18c1b9dcda47e2ca68e3f`; the sanitized equivalent is
`4dc3feb625f824b9062e162808fd74b07e97c404`.

No remote existed, so no published history was force-pushed. The private backup
is not part of this repository and must remain private. The annotated `v0.6.0`
tag identifies the sanitized baseline.

## Safe regression fixtures

Tests may store card names, seeds, expected public choices, and deterministic
state recipes. They must generate private Game Records only in temporary
directories and verify that saved records contain no raw capabilities. A
historical record may be characterized by a sanitized recipe; the checkpoint
itself remains local.
