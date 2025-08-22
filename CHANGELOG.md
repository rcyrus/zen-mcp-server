# CHANGELOG

<!-- version list -->

## v5.10.0 (2025-08-22)

### Chores

- Sync version to config.py [skip ci]
  ([`1254205`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/12542054a214022d3f515e53367f5bf3a77fb289))

### Features

- Refactored and tweaked model descriptions / schema to use fewer tokens at launch (average
  reduction per field description: 60-80%) without sacrificing tool effectiveness
  ([`4b202f5`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/4b202f5d1d24cea1394adab26a976188f847bd09))


## v5.9.0 (2025-08-21)

### Documentation

- Update instructions for precommit
  ([`90821b5`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/90821b51ff653475d9fb1bc70b57951d963e8841))

### Features

- Refactored and improved codereview in line with precommit. Reviews are now either external
  (default) or internal. Takes away anxiety and loss of tokens when Claude incorrectly decides to be
  'confident' about its own changes and bungle things up.
  ([`80d21e5`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/80d21e57c0246762c0a306ede5b93d6aeb2315d8))

### Refactoring

- Minor prompt tweaks
  ([`d30c212`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/d30c212029c05b767d99b5391c1dd4cee78ef336))


## v5.8.6 (2025-08-20)

### Bug Fixes

- Escape backslashes in TOML regex pattern
  ([`1c973af`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/1c973afb002650b9bbee8a831b756bef848915a1))

- Establish version 5.8.6 and add version sync automation
  ([`90a4195`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/90a419538128b54fbd30da4b8a8088ac59f8c691))

- Restore proper version 5.8.6
  ([`340b58f`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/340b58f2e790b84c3736aa96df7f6f5f2d6a13c9))

### Chores

- Sync version to config.py [skip ci]
  ([`4f82f65`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/4f82f6500502b7b6ba41875a560c41f6a63b683b))


## v1.1.0 (2025-08-20)

### Features

- Improvements to precommit
  ([`2966dcf`](https://github.com/BeehiveInnovations/zen-mcp-server/commit/2966dcf2682feb7eef4073738d0c225a44ce0533))


## v1.0.0 (2025-08-20)

- Initial Release
