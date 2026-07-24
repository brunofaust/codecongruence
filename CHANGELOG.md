# CHANGELOG


## v0.7.0 (2026-07-24)

### Build System

- **deps**: Upgrade locked python dependencies
  ([`621fb90`](https://github.com/brunofaust/codecongruence/commit/621fb90c979266f5532231e46f08d5283cccad39))

26 packages upgraded within existing pyproject constraints via uv lock --upgrade; suite green (204
  passed) on new versions.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MALyFpeEeK1JZfW8i3xUU5

### Chores

- **quality**: Restore rule imports, allowlist protocol param, target mypy at 3.12
  ([`91e64bb`](https://github.com/brunofaust/codecongruence/commit/91e64bb19d8b4a3bc394c7ed997072200577ed6d))

Restore RuleViolation import in D003 and D004 rules (needed for return type annotations in
  Sequence[RuleViolation]). Add vulture allowlist for EmbeddingBackend.batch_size Protocol param.
  Target mypy at Python 3.12 to match resolved venv + numpy 2.5.1 PEP 695 type stubs.

### Features

- **deps**: Raise dependency floors to latest and require Python 3.12+
  ([`40d4a0a`](https://github.com/brunofaust/codecongruence/commit/40d4a0a178ebb6c439a0101a70340e8f1eefcc67))

Floors in [project.dependencies] and the dev group now match the latest releases (numpy 2.5.1,
  pydantic 2.13, fastembed 0.8, ...); Python 3.11 support is dropped since numpy >=2.5.1 requires
  3.12; prek/pyupgrade/ruff/mypy all now target the 3.12 baseline; 211 tests and both prek stages
  green.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MALyFpeEeK1JZfW8i3xUU5

### Performance Improvements

- **embedder**: Cap ONNX inference batch size to bound peak memory
  ([`1d32d57`](https://github.com/brunofaust/codecongruence/commit/1d32d57873ca887aa37982168882fb3da645cc8e))

fastembed's default batch_size=256 let a single embed call allocate ~5.7 GB of activation buffers
  that ONNX Runtime's arena never returns, so parallel codecongruence processes each pinned 6 GB.
  New embed_batch_size config option (default 16) caps peak RSS under ~1 GB with no measurable
  throughput cost.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MALyFpeEeK1JZfW8i3xUU5

### Refactoring

- **rules**: Extract shared rule helpers and single-source config defaults
  ([`e391953`](https://github.com/brunofaust/codecongruence/commit/e39195328ce19d17d4abbca6beadbc247d909288))

Extract shared helpers (resolve_threshold, iter_parsed, similarity_violation) into base.py to
  consolidate ~150 duplicated lines across 9 rule modules. Single-source config defaults (model,
  embed_batch_size, cache_ttl_days) as constants in config.py; load_config uses model_validate for
  Pydantic defaults. Bump cache-persistence logging to warning. Runner precomputes rule config once,
  shared between parallel and sequential branches.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MALyFpeEeK1JZfW8i3xUU5


## v0.6.0 (2026-07-03)

### Bug Fixes

- **cli**: Anchor the process at the repo root before running rules
  ([`01cf278`](https://github.com/brunofaust/codecongruence/commit/01cf2786a980f9cd28bf06383eabd0e4886904e8))

git reports changed paths relative to the repo root while rules read them relative to the invocation
  directory, so running codecongruence from a subdirectory silently checked nothing. The CLI now
  resolves user-supplied paths against the invocation directory, then chdirs to the repo root for
  the run (both the check command and init's pre-embedding pass). Also switches the CLI off
  Embedder._cache in favour of the new cache_size property.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **config**: Read cache_ttl_days from the TOML section
  ([`8b998eb`](https://github.com/brunofaust/codecongruence/commit/8b998eb8807a7522fb4ce2678ebe9b1567f75c99))

load_config never passed cache_ttl_days through to CodeCongruenceConfig, so the value documented in
  DEFAULT_TOML and the example config was silently ignored and the embedding-cache TTL was always
  the 30-day default.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **embedder**: Remove the on-disk cache file when cleanup empties it
  ([`0e71c62`](https://github.com/brunofaust/codecongruence/commit/0e71c62308ab9c65aad97efe9e7032bb51659244))

save(force_cleanup=True) deleted every entry from the in-memory cache but _save_disk_cache
  early-returned on an empty cache, leaving the stale embeddings.npz behind — the next run would
  resurrect the evicted entries.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **init**: Install the Claude Code skill at its standard location
  ([`3b322e4`](https://github.com/brunofaust/codecongruence/commit/3b322e4eb1b4c45c5a2e40a9cedb1228759b5a4d))

The skill template was written to claude/skills/codecongruence.md, a path Claude Code never reads.
  Claude Code discovers project skills at .claude/skills/<name>/SKILL.md, so init now writes it
  there. The repo's own installed copy is moved accordingly and docs updated.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **release**: Land the version bump via the PR, tag-only publish
  ([`85ef2ff`](https://github.com/brunofaust/codecongruence/commit/85ef2ff9fabc9154188aa980c91c387061dcc35a))

`main` is protected, so python-semantic-release's `version` step (which commits the bump and `git
  push`es it to `main`) is rejected with GH006. That path was introduced after v0.5.0 (commit
  b379730 removed the earlier `--no-commit`) and first actually ran when v0.6.0's release PR merged
  -> the release failed.

Split the workflow so nothing pushes to protected `main`:

- prepare (push to release/**): PSR generates the version bump + CHANGELOG on the release branch; it
  lands on `main` through the PR merge. Loop-guarded by comparing the computed version to pyproject,
  so the bump commit no longer needs `[skip ci]` and CI validates the release PR. - publish (release
  PR merged): read the version from `main`'s pyproject, create + push the vX.Y.Z tag (tags are not
  branch-protected) and the GitHub release from the CHANGELOG. Never pushes to `main`.

Add a release/* PSR branch group so it computes the (non-prerelease) version on the release branch.
  Update the CLAUDE.md release runbook. No bypass token or branch-protection change required.

- **release**: Let semantic-release land the version bump on main
  ([`b379730`](https://github.com/brunofaust/codecongruence/commit/b379730f29aecfbc40685976c2ad1952207c2f04))

The workflow ran 'semantic-release version --no-commit', so the pyproject.toml bump and CHANGELOG
  that PSR generated were discarded — main stayed at 0.1.1 while tags advanced to v0.5.0, and the
  configured 'chore(release): v{version}' commit_message was never used. Check out main explicitly
  (pull_request events sit on a detached merge ref), give the runner a git identity, and let PSR
  commit and push. pyproject.toml is realigned to the already-released 0.5.0; PSR derives the next
  version from tags, so this is metadata repair, not a release.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **rules**: Stop depending on the process working directory
  ([`382503e`](https://github.com/brunofaust/codecongruence/commit/382503e06b9a2d3e90a1f95ce5f211273b7c3807))

git reports paths relative to the repo root, but rules read files and ran git diffs relative to the
  process cwd, so library callers had to chdir into the repo first. ChangedFile now carries its
  repo_root (with an abs_path helper that the default "." keeps cwd-relative for direct
  constructions), file reads resolve through it, and every git call inside rules passes an explicit
  cwd. Reported paths stay repo-relative so baselines remain machine-independent — including C003
  scope="full", which previously reported absolute paths.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **runner**: Reject unknown --rule ids and accept short codes
  ([`50394af`](https://github.com/brunofaust/codecongruence/commit/50394af30f271d329997bb5c1e4ce0603e81b3a1))

An unknown --rule id silently selected zero rules and exited 0, so a typo in a pre-commit hook
  disabled checking without anyone noticing. select_rules (now public) raises UnknownRuleError
  listing the valid rules, and the CLI exits 2. It also accepts short codes (D001) as the CLI docs
  always claimed, and documents that an explicit --rule runs the rule even when disabled in config.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

### Chores

- **release**: Prepare v0.6.0
  ([`e505dec`](https://github.com/brunofaust/codecongruence/commit/e505dec4b21d052e0ba1e0fd308ecaa0979cd7e2))

### Continuous Integration

- Bump GitHub Actions off deprecated Node 20 runtimes
  ([`908528b`](https://github.com/brunofaust/codecongruence/commit/908528b2730eb6d2ab535e7908e9a819d0da7caf))

actions/checkout@v4 and astral-sh/setup-uv@v3 run on Node 20, which GitHub forces to Node 24 on June
  16, 2026 and removes from runners on September 16, 2026. checkout moves to v6; setup-uv is pinned
  to the immutable v8.2.0 tag since the project stopped publishing moving tags.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **prek**: Exclude the generated CHANGELOG.md from mdformat and typos
  ([`c83453c`](https://github.com/brunofaust/codecongruence/commit/c83453c71872b0443b6c3759b8b864b85cee601d))

python-semantic-release regenerates the full CHANGELOG on every release; its markdown formatting and
  commit-SHA links (short hex hashes read as typos) fail mdformat and typos. Exclude it — its format
  is PSR's contract, not hand-edited.

- **release**: Auto-bump the docs rev examples on every release
  ([`b8b78a9`](https://github.com/brunofaust/codecongruence/commit/b8b78a9883c1ab0d39a29d23ecc787026327691d))

version_variables with tag format ('docs/...:rev:tf') makes python-semantic-release rewrite the
  pinned rev: examples in docs/usage/prek.md and docs/usage/pre-commit.md when it bumps the version,
  so the docs can never drift behind the latest release again. linters.md is deliberately excluded —
  it pins other repos' revs in the same file. Verified with a local 'semantic-release version' dry
  run (0.5.0 → 0.5.1 rewrote both docs, left linters.md untouched).

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

### Documentation

- Fix dev install command in CLAUDE.md
  ([`54eca12`](https://github.com/brunofaust/codecongruence/commit/54eca12d20b780d0e1071cf407bc886c3a89153b))

Dev dependencies live in [dependency-groups], which uv sync includes by default; there is no 'dev'
  extra, so 'uv sync --extra dev' fails.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- Install via `uv tool` from GitHub; add C003 path-fidelity guidance
  ([`85535b8`](https://github.com/brunofaust/codecongruence/commit/85535b82d6e48678f74b2661c9ed7d2d11043f97))

codecongruence is not published to PyPI, so the README's `pip install codecongruence` instructions
  never worked. Replace them with `uv tool install` from the GitHub URL (the unpinned form tracks
  main, where releases land; a @vX.Y.Z placeholder shows how to pin a release).

Also add an "Acting on a violation — never confabulate the path" section to all three AI-context
  templates and their installed copies. Under pre-commit capture there is no TTY, so the rich
  violation table falls back to 80 columns and a C003 message (which carries two file:line pairs)
  folds mid-path — easily misread and reconstructed wrong. The guidance tells assistants to re-run
  `--format json` for authoritative file_path/line, copy verbatim, and confirm the path exists.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01BAMtgkSbXEJtLoXroNWXRy

- Refresh test count, offline prek hint, --rule exit code
  ([`52325ae`](https://github.com/brunofaust/codecongruence/commit/52325ae7558f1b0822be72075084cf6036182977))

CLAUDE.md said ~100 tests (there are ~190) and offered no way to run the quality gate on restricted
  networks where the gitleaks hook cannot download Go (SKIP=gitleaks). The CLI reference documents
  that unknown --rule values exit 2.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- **usage**: Pin current rev in hook examples, explain why not 'latest'
  ([`4671d6e`](https://github.com/brunofaust/codecongruence/commit/4671d6ee6d7f209a3085eddd2e15d73f131c8b15))

The prek and pre-commit usage docs showed rev: v0.1.0 and never said why a moving 'latest' ref is
  unsupported: both runners cache the hook environment keyed by rev, so a mutable ref silently
  freezes on the first-installed commit. Examples now show v0.5.0, prek.md gains the prek-native
  prek.toml snippet, and both docs point to prek auto-update / pre-commit autoupdate (plus
  pre-commit.ci or Renovate for hands-off bumps). linters.md notes its chain revs are illustrative.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

### Features

- **cache**: Share the primary worktree's embeddings as a read-only base
  ([`4a69511`](https://github.com/brunofaust/codecongruence/commit/4a69511232d4dc7dd6014a1e1ee147969087b77e))

Linked git worktrees cold-started the embedding cache: .codecongruence/ is gitignored, so `git
  worktree add` never copies it and a fresh checkout re-embedded the whole corpus. Because the cache
  key is a content hash (model-independent), an embedding computed in one checkout is valid in every
  other, so layer the primary worktree's cache underneath the local one as a read-only base.

- git.main_worktree_root() resolves the primary worktree via `git worktree list`. - Embedder gains
  base_cache_dir: the base warms the run but save() persists only locally-owned (non-base) keys, so
  the base is never duplicated or mutated and force_cleanup prunes only local keys. - Writes go
  through _atomic_savez (temp file + os.replace) so a worktree reading the base can't observe a torn
  file. - cli.make_embedder wires both; the primary worktree (base == local) keeps today's
  single-cache behaviour.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01BAMtgkSbXEJtLoXroNWXRy

### Refactoring

- Drop module-level `_`-prefixes per the repo style rule
  ([`7a7c744`](https://github.com/brunofaust/codecongruence/commit/7a7c744d4486b28591b7e102bbd40e73f31942e2))

CLAUDE.md and brunofaust-python-style both require module-level names to avoid a leading underscore
  (the prefix blinds vulture/ruff/pyright to module-scope dead code) and to control visibility via
  __all__ instead. Rename the private module-level helpers this branch touches:

- cli.py: _ensure_gitignore_entry, _version_callback, _purge_models_callback, _init_setup, _run ->
  drop the underscore. - embedder.py: _hash -> hash_text (avoids shadowing the builtin), _CACHE_FILE
  -> CACHE_FILE. - git.py: _run_git -> run_git, _HUNK -> HUNK.

None are exported in __all__, so the public API is unchanged (same pattern as the existing
  OutputFormat). De-underscoring re-exposed these to the interrogate docstring gate, so add the
  missing Google-style docstrings.

- **embedder**: Expose public embed_batch() and cache_size
  ([`95ce445`](https://github.com/brunofaust/codecongruence/commit/95ce445b0af498d2350dc309591fa3eaad0a62c7))

Rule C003 reached into Embedder._embed_locked via asyncio.to_thread and re-imported Embedder inside
  its comparison loop just to call the static cosine helper. A public async embed_batch() and a
  cache_size property give rules and the CLI a supported surface instead of private attributes.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

### Testing

- Extend the strict mypy gate to tests/
  ([`6b2335c`](https://github.com/brunofaust/codecongruence/commit/6b2335ca9951c3acd2635c85c8227061d3dbca8a))

CLAUDE.md claims 'mypy --strict must pass' but the gate only checked src/. Add tests/ to mypy files
  and fix the fallout: return annotations on the per-rule _check/_run helpers, typed kwargs, the
  Rule protocol on parametrized fixtures, and one stale type: ignore.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- Isolate throwaway git repos from host git configuration
  ([`6eab9c3`](https://github.com/brunofaust/codecongruence/commit/6eab9c3b49a056de302044a01c8d4c1ae9653baf))

base_git_env now points GIT_CONFIG_GLOBAL at /dev/null and sets GIT_CONFIG_NOSYSTEM so host-level
  settings (commit signing, hooks, templates) cannot break test commits. The init CLI test also
  passes --no-download so the suite never touches the real embedding model.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY

- Strip ANSI escapes before asserting on CLI help output
  ([`013fab5`](https://github.com/brunofaust/codecongruence/commit/013fab5dab34297a8c46a02c93a350855cd2e000))

On CI runners with FORCE_COLOR set, rich splits tokens like --config across ANSI style segments, so
  the raw substring never appears in the captured stdout and the help-text assertion fails.

https://claude.ai/code/session_01BhLoSGi2ipWdTNhagAMYCY


## v0.5.0 (2026-05-25)

### Bug Fixes

- **agents**: Restore YAML frontmatter and protect from mdformat
  ([`a2733e5`](https://github.com/brunofaust/codecongruence/commit/a2733e5dd9a357af9bed8e2f0cec1303f6fbafd4))

The YAML frontmatter in codecongruence.md was mangled by mdformat into a horizontal rule plus
  collapsed heading. Restored proper `---` delimiters and added src/codecongruence/agents/** to
  mdformat exclude list to prevent future formatting of agent template files.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **prek**: Exclude .git/** from remove-tabs hook
  ([`d29723e`](https://github.com/brunofaust/codecongruence/commit/d29723ec443bcb50e5dd68a171f32c0e2d27a9e2))

The remove-tabs hook was converting git config's standard tab-indented values to spaces, breaking
  prek --all-files runs from stop hooks. Also adds .git/** to the global prek exclude pattern.

### Chores

- Add self-generated AI context files (codecongruence eats own dogfood)
  ([`8cc8bfd`](https://github.com/brunofaust/codecongruence/commit/8cc8bfd042e96063db28ba672ed529f5ce9db2a8))

- Fix ruff F401 and update baseline for C003 in test_embedding_cache
  ([`d0fc049`](https://github.com/brunofaust/codecongruence/commit/d0fc04910251a0d87cc6c3ccce14b8498f8a8e50))

Remove unused `import time` in test_embedding_cache.py (ruff F401). Update baseline to suppress 8
  pre-existing C003 violations in that file — the cache test functions are intentionally similar
  (test different scenarios of the same component), so C003 is a false positive there.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **release**: Prepare v0.5.0
  ([`e2bb220`](https://github.com/brunofaust/codecongruence/commit/e2bb2203f539f7cfb530fe9880cee656787ed0e4))

### Continuous Integration

- **release**: Gate PSR on release/ branch merges only
  ([`a26ede1`](https://github.com/brunofaust/codecongruence/commit/a26ede130f885b7629d127a826c95a1e4a25d733))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Documentation

- Update docs & restore AI context files from bundled templates
  ([`316a8c6`](https://github.com/brunofaust/codecongruence/commit/316a8c6f87d1c4c1796880126c48f40755fbdae1))

- Updated CLAUDE.md, ARCHITECTURE.md, README.md, TODO.md, and all docs/ files for accuracy (9 rules
  not 8, baseline path, prek install, etc.) - Moved baseline from repo root to
  .codecongruence/.codecongruence-baseline.json with gitignore negation for tracking - Restored
  3-file AI context install (claude/skills, .cursor/rules, AGENTS.md) from bundled
  src/codecongruence/agents/ templates via importlib.resources - Fixed C003 rule missing docs_url
  protocol attribute - Switched prek mypy hook to local system hook (uv run mypy) for full project
  venv — eliminates unused-ignore/missing-dep discrepancy - Added mypy>=1.16 to dev dependencies and
  pydantic.mypy plugin to mypy config - Removed stale .claude/ dir ref from ruff exclude list -
  Added hatchling include for agents directory so AI context files are bundled in wheel - Fixed YAML
  frontmatter in codecongruence.md skill file

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Features

- **cli**: Add --update-baseline for incremental adoption
  ([`9e94b12`](https://github.com/brunofaust/codecongruence/commit/9e94b124632345c2a86110d496b127fc60811053))

Adds a .codecongruence-baseline.json that stores violations by (rule_id, file_path, line).
  --update-baseline saves all current violations and exits 0; subsequent runs suppress baseline
  entries and only fail on new violations. Teams can adopt codecongruence on existing codebases
  without fixing everything at once.

Also fix git env-var leakage in production git.py (_run_git) and in test helpers: prek hook runner
  sets GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE which leaked into child git repos created during tests.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **init**: Write AI context files for Claude Code, Cursor, and Codex
  ([`04a628d`](https://github.com/brunofaust/codecongruence/commit/04a628dd5eb6d781dfb9212a27c29acd00e55cb5))

`codecongruence init` now writes three files that teach AI coding assistants about every rule and
  how to fix violations: - .claude/skills/codecongruence.md — Claude Code skill -
  .cursor/rules/codecongruence.mdc — Cursor MDC rule - AGENTS.md — OpenAI Codex section (appended or
  created)

Files are skipped if they already exist; --force overwrites.

Also fixes all git subprocess helpers across the test suite and _run_git in core/git.py to strip
  prek-injected hook env vars (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE) via base_git_env(),
  preventing index corruption and wrong-repo lookups during prek runs.

- **rules**: Add docs_url to violations for AI-friendly error messages
  ([`2a518ed`](https://github.com/brunofaust/codecongruence/commit/2a518ed20cb51991532a231654a842f71b12c979))

Each RuleViolation now carries a docs_url pointing to that rule's README (with bad/good examples).
  The runner injects it post-hoc via dataclasses.replace() — zero changes needed in rule check()
  methods. The text reporter prints a deduplicated "Rule documentation:" section after the violation
  count so AI agents can self-correct.

Also fix git env-var leakage in tests: prek hook runner sets GIT_DIR / GIT_INDEX_FILE /
  GIT_WORK_TREE which bled into child git repos created by integration tests. Added base_git_env()
  helper to conftest.py that strips those vars before spawning child git processes. Extended fix to
  git.py _run_git() which also needed to strip these vars.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.4.0 (2026-05-25)

### Features

- **cache**: Add GC for embedding cache — compact on --all, TTL eviction at load
  ([`070616d`](https://github.com/brunofaust/codecongruence/commit/070616d7e6e038333432f719d980926049a71bd2))

Implement embedding cache garbage collection with two mechanisms: - TTL-based eviction: stale
  entries (>30 days) removed on load - Compaction: `compact()` called after `--all` runs to remove
  unused files

Tracks last-used and first-seen timestamps in NPZ metadata. Compaction yields significant space
  savings on repeated runs. TTL is configurable via `cache_ttl_days` in config; disabled when set to
  0.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Refactoring

- **cache**: Write-once-on-exit — embed() in-memory only, save() at end of run
  ([`b36a3d5`](https://github.com/brunofaust/codecongruence/commit/b36a3d51f09bb5c088b4740304050772fe740333))

Simplify cache write strategy: embed() no longer touches disk, keeping the hot path fast. All
  in-memory embeddings persist once via save() at end of run, called unconditionally in _run() and
  after pre-embedding in _init_setup(). Replaces compact() with save(*, force_cleanup=bool) — the
  single disk-write point. When force_cleanup=True (--all scans), stale entries are removed; when
  False, full cache is persisted as-is. Tests updated: new test_embed_stays_in_memory, all tests
  call save() explicitly before reloading from disk.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.1 (2026-05-25)

### Documentation

- **claude**: Document .npz cache format and content-hash key semantics
  ([`fed791f`](https://github.com/brunofaust/codecongruence/commit/fed791f9e36c866eaad6ffd0682c31b9a2d639eb))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Performance Improvements

- **embedder**: Swap embedding cache from JSON.gz to .npz
  ([`c293fa9`](https://github.com/brunofaust/codecongruence/commit/c293fa9a51a87ab48d9f0ae77e42579de9d47305))

Binary float32 storage is ~2-3x smaller and faster to load than JSON-encoded floats. Removes
  gzip/json imports. Pads variable-length vectors to max_dim before stacking so the cache is valid
  even when backends produce vectors of different sizes. Existing embeddings.json.gz files are
  silently ignored; the cache rebuilds.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.0 (2026-05-25)

### Features

- **rules**: Add C003 duplicate_functions rule
  ([`057a600`](https://github.com/brunofaust/codecongruence/commit/057a6006c9ae1526e486cb0889405593e75e377e))

Flags pairs of functions with different names whose bodies are semantically identical (cosine
  similarity >= threshold). Configurable scope: "staged" (default, compares staged functions only)
  or "full" (scans every tracked file — good for periodic audits). All bodies embedded in a single
  batch call; pairwise cosines computed in pure NumPy. Default threshold 0.92,
  min_body_statement_count 3.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.2.1 (2026-05-24)

### Bug Fixes

- **release**: Filter maintenance commits from release notes
  ([`b65eabe`](https://github.com/brunofaust/codecongruence/commit/b65eabe115d551125f42c7e6b5f89fe8f50d1662))

Only feat/fix/perf are user-facing. Exclude chore/docs/test/build/ci/ refactor/style from the
  PSR-generated GitHub release body.


## v0.2.0 (2026-05-24)

### Bug Fixes

- Complete docstring Args coverage and add config reference example
  ([`78cf69b`](https://github.com/brunofaust/codecongruence/commit/78cf69bfa06991e0e9da1ecef2c870ede6ab1e11))

All D417 (pydoclint Args completeness) violations fixed across src/. Add codecongruence.toml.example
  as the canonical annotated reference for every configuration option. Update rule table in all docs
  (D005 is docs_on_change, D006 params_in_docstring is now listed). Fix ruff config: PLR0912 added
  for python.py match statement; PLW0717/RUF067 confirmed as valid preview rules.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Force deterministic terminal width in CliRunner for CI
  ([`114bb31`](https://github.com/brunofaust/codecongruence/commit/114bb31a7f09f9f1d0575a2a1108ad8e0024682c))

CI (no TTY) lets Rich pick terminal width via os.get_terminal_size(), which can return a narrow or
  zero value on some runners, causing help text to reflow and truncating option names like --config.
  Setting COLUMNS=200 and NO_COLOR=1 on the fixture makes help-text assertions consistent across
  macOS and Ubuntu CI.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **cli**: Pass repo root to default_config_path in init_cmd
  ([`4821fbe`](https://github.com/brunofaust/codecongruence/commit/4821fbea9b2926e86513ed3a558d280d6aa974ca))

init_cmd was calling default_config_path() without the git repo root, causing it to fall back to cwd
  instead of the discovered repo root when invoked from a subdirectory. Now passes
  asyncio.run(current_repo_root()) to match the behavior in _run(). Updated docstring to document
  path and force parameters. Added CHANGELOG entry.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **cli**: Remove gitignore mutation from hook hot path
  ([`f085783`](https://github.com/brunofaust/codecongruence/commit/f0857831168dc68053453a07251717f25b8045db))

The hook was calling _ensure_gitignore_entry() on first run to add .codecongruence to .gitignore.
  Since .gitignore is a tracked file, prek would fail with "files were modified by this hook".
  Gitignore updates now happen only during `codecongruence init`, not as a side-effect of the hook's
  execution path.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **cli**: Restore click's default error handling
  ([`ed7cddd`](https://github.com/brunofaust/codecongruence/commit/ed7cddd192feb910d0367229ae7a06db1101755c))

Removed `standalone_mode=False` and the now-unused `sys` import. With `standalone_mode=False`, Click
  does not catch UsageError, so typos like `innit` instead of `init` produce a raw Python traceback.
  With the default `standalone_mode=True`, Click handles all user errors gracefully—prints a clean
  error message with suggestions (e.g. "Did you mean 'init'?") and exits with code 2.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **release**: Isolate PSR from dev deps to prevent typer downgrade
  ([`c334839`](https://github.com/brunofaust/codecongruence/commit/c334839910e0909e2b4337b463ca3c31ea94c6f9))

python-semantic-release and commitizen pulled in click 8.1.8 and typer 0.23.1, breaking
  test_help_lists_init_subcommand in CI (no-TTY renders help at 80 cols, --config was missing from
  output). PSR now installs via uv tool in release.yml; commitizen hooks run via prek's ecosystem.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>

- **release**: Pin python-semantic-release to v9 to preserve major_on_zero
  ([`d5bf6da`](https://github.com/brunofaust/codecongruence/commit/d5bf6dac766d9afece5e298c40283ceaf66f4724))

PSR v10 dropped major_on_zero, causing v1.0.0 instead of v0.2.0. Pin to >=9,<10 so the config is
  respected.

- **release**: Set build_command to empty string for PSR config
  ([`576b623`](https://github.com/brunofaust/codecongruence/commit/576b623e9a7406f5891ce7c77aad7f721cdd3ba6))

- **release**: Use --no-commit to avoid pushing to protected main branch
  ([`5f6af9c`](https://github.com/brunofaust/codecongruence/commit/5f6af9c873bc50b6a8ed7950623103f6be6d5d25))

PSR's version commit push is blocked by branch protection on GitHub Free (no bypass-actors support).
  --no-commit skips the version-bump commit but still creates and pushes the git tag (tags bypass
  branch protection). PSR uses git tags as authoritative version source for subsequent releases.

- **reporters**: Warn when no staged files found instead of silent exit
  ([`d42cabc`](https://github.com/brunofaust/codecongruence/commit/d42cabcd4d1cd1572d006955610e490e7c3e15fc))

Previously, TextReporter would exit silently (code 0) when no staged files were present, misleading
  users into thinking the check passed when it had actually performed no validation. Now it prints
  an explicit yellow warning before returning, making the "nothing to check" state obvious.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **test**: Set COLUMNS env var for Rich terminal detection in CI
  ([`d98bc61`](https://github.com/brunofaust/codecongruence/commit/d98bc617b38796d0b4758aee4784553e530a461c))

The test_help_lists_init_subcommand test was failing in headless CI because Rich's terminal-width
  detection couldn't determine TTY dimensions. Setting COLUMNS=200 explicitly ensures consistent
  table formatting in non-interactive environments.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **test**: Set COLUMNS env var for Rich terminal detection in CI
  ([`b9880db`](https://github.com/brunofaust/codecongruence/commit/b9880dba3373d0ec4418d37c8bb3fe58fe68d217))

The test_help_lists_init_subcommand test was failing in headless CI because Rich's terminal-width
  detection couldn't determine TTY dimensions. Setting COLUMNS=200 explicitly ensures consistent
  table formatting in non-interactive environments.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Documentation

- Clarify staged-files-only default and --all flag in README
  ([`5de7db8`](https://github.com/brunofaust/codecongruence/commit/5de7db8b0fa9cfb73930f98a2607ffb9485643f9))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Fix installation instructions and development workflow
  ([`0e53a15`](https://github.com/brunofaust/codecongruence/commit/0e53a15173732a07d57aec877040bfa260b0ec8f))

Remove incorrect claim that codecongruence is a pip package; it's installed via pre-commit / prek
  hooks. Rewrite Quick start with correct hook-based setup, and consolidate code quality checks into
  single prek invocation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Fix README rule count heading and add missing C002 row
  ([`53cf3d6`](https://github.com/brunofaust/codecongruence/commit/53cf3d61e2dc4529b39d7b550188940329bdb79c))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Features

- **cli**: Add --purge-models option to delete embedded model cache
  ([`aaa5393`](https://github.com/brunofaust/codecongruence/commit/aaa53936a79a68c1b265367cde50087f157fdc37))

Users can now run `codecongruence --purge-models` to delete the ~/.cache/codecongruence directory
  (containing cached sentence-embedding models) and exit cleanly. Useful for debugging, CI/CD image
  cleanup, or freeing disk space.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **D001**: Add include_comments config to strip comments before embedding
  ([`c492f16`](https://github.com/brunofaust/codecongruence/commit/c492f16ffe5dd2c1861cb8d3037743d7638ca3ff))

Added `include_comments` config option (default False) that strips inline comments from function
  body before embedding, preventing comment text from inflating similarity scores and masking real
  docstring drift. Migrated config reads to `getattr()` for Bandit compatibility. Renamed
  `_DEFAULT_TOML` → `DEFAULT_TOML` per style guide.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **prek**: Add semantic hook for codecongruence execution
  ([`b04c5ea`](https://github.com/brunofaust/codecongruence/commit/b04c5ea7492e639885802e6fe6083530a880ee11))

- **release**: Add automated semantic-release pipeline
  ([`197f1be`](https://github.com/brunofaust/codecongruence/commit/197f1be3ecb517af2e9c111f6675c5a4b0b6cc8a))

python-semantic-release runs on push to main, reads conventional commits, bumps pyproject.toml
  version, writes CHANGELOG.md, and creates a GitHub release + git tag. commitizen prek hook
  validates commit format locally. D005 updated to no longer require CHANGELOG.md in docs_files.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **rules**: Add include_comments config to C001, C002; extract strip_comments to base
  ([`ade7627`](https://github.com/brunofaust/codecongruence/commit/ade762709f258db3799f750308dce442dae007d2))

Consolidate inline-comment handling by moving INLINE_COMMENT_RE and strip_comments() from
  D001_docstring_vs_body to rules/base.py. Add per-rule include_comments config:

- C001 (name_vs_body): default false — strip comments before embedding name vs body, so a stray
  comment does not inflate similarity and mask real drift. - C002 (param_name_vs_usage): default
  true — keep comments in usage context, since a comment like "# validate user_id" is real semantic
  signal about the parameter.

Updated both rule READMEs, example config, CHANGELOG.md, and added 4 new test cases (2 per rule)
  demonstrating the behavior with and without comments included.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.1.0 (2026-05-23)

### Bug Fixes

- **cli**: Remove future annotations to resolve typer parameter discovery in CI
  ([`3a56d27`](https://github.com/brunofaust/codecongruence/commit/3a56d2718d5e48cb4b6ce4bc1d9948f1b506a244))

Typer 0.25+ uses inspect.signature() at import time to resolve function parameters. With __future__
  annotations enabled, Path | None becomes the string "Path | None" instead of a live
  types.UnionType object, causing get_type_hints() to fail in subprocess CI environments without TTY
  access. Removing the future import allows typer to correctly discover and register the --config
  parameter across all environments.

Also removed the now-redundant noqa comment on the Path import.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- **docs**: Adjust formatting and improve clarity in CLAUDE.md and research.md
  ([`f4b95e7`](https://github.com/brunofaust/codecongruence/commit/f4b95e7da11291d681ee5a35128bd53568df9a4d))

### Chores

- **config**: Update tool configs and add OutputFormat docstring
  ([`cc4f35e`](https://github.com/brunofaust/codecongruence/commit/cc4f35e31ea82361b623a20ac131072bca0e2cf3))

- Add docstring to OutputFormat class in cli.py for clarity - Remove
  validate-pyproject-schema-store[all] from prek.toml (SchemaStore ruff schema was out of date) -
  Add documents parameter to vulture ignore_names in pyproject.toml - Exclude
  D005_changelog_exists/README.md from mdformat (known mdformat bug with plugin rendering)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Continuous Integration

- Remove push trigger, run CI only on pull_request
  ([`d8e4fa0`](https://github.com/brunofaust/codecongruence/commit/d8e4fa047f5ae5c8992dceb86a50205f7553c402))

Eliminates duplicate CI runs on merge to main. Workflow now executes only on pull_request events,
  not on direct push to main.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Simplify to prek run --all-files, add pytest to default stage
  ([`71373b9`](https://github.com/brunofaust/codecongruence/commit/71373b9ebc1165751ef69fe0d3ec785f8c5d3cb3))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Use mirrors-mypy remote hook, prek in dev deps, minimal CI
  ([`abc9f46`](https://github.com/brunofaust/codecongruence/commit/abc9f46a0d25e6f64f682cf27b700e52427248a2))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

### Features

- Excludes, runner-as-contract, gitignore auto-update, CI simplification
  ([`01d4a61`](https://github.com/brunofaust/codecongruence/commit/01d4a615802857146e849bd6e96b5d4a594ad7db))

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- File/function excludes, runner-as-contract, gitignore auto-update
  ([`bcf03b2`](https://github.com/brunofaust/codecongruence/commit/bcf03b2bb3870a840dc5f221ce5922659a63b88d))

- Add global + per-rule file/folder excludes (glob patterns) to config system - Add per-rule
  function-level excludes (fnmatch) for fine-grained filtering - Runner-as-contract: function
  exclusion computed once; ChangedFile.iter_functions/iter_comments transparently filter excluded
  ranges - Rules have zero exclusion logic; they call cf.iter_functions(parser, source) instead of
  parser.iter_functions directly - Add .codecongruence to .gitignore on folder creation (init_cmd +
  first _run) - Add CODEOWNERS file (.github/CODEOWNERS) - Fix 73+ ruff lint errors (DOC, D, ANN,
  PLR, PLC) and 1 mypy error - Add D006 params_in_docstring rule for parameter presence + ordering
  checks - Improve C002 param_name_vs_usage rule - Set Python minimum version to 3.11 - 92 tests
  passing; all rules integrated and tested

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- Update CI configuration, refine dependency management, and improve code structure
  ([`ae021dd`](https://github.com/brunofaust/codecongruence/commit/ae021ddd5d373205d53da4887eea5433de94ffa0))
