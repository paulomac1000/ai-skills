# Local hook pitfalls

- Running network or credentialed integration tests before every commit.
- Duplicating formatter or linter configuration in hook arguments.
- Passing changed filenames to a repository-wide check that then misses errors.
- Running all CI checks locally instead of respecting a measured latency budget.
- Treating hook installation as a security boundary; CI remains authoritative.
- Using an unreviewed baseline that hides new secrets.
- Pinning a hook in prose instead of the hook manifest.
- Auto-fixing files without showing the developer what changed.
