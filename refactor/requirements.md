# Requirements (LLM‑Executable)

**Scope:** Optimize the Zen MCP Server *simulator* test suite to reach <10 min full, <3 min PR/quick, while preserving “live spec” value. These requirements replace library‑specific mentions with a **Unified Cassette System** so agents can choose the best backend while meeting the same acceptance criteria. Source alignment: faster_sim.md, prior requirements, design, and tasks. fileciteturn0file3 fileciteturn0file2 fileciteturn0file1 fileciteturn0file0

## Terminology
- **Unified Cassette System (UCS):** A deterministic recording/replay layer for HTTP across **requests**, **httpx**, and **aiohttp**. Backends: *responses* or *requests‑mock* (requests), *respx* (httpx), *aioresponses* (aiohttp). citeturn0search18turn0search3turn0search1turn0search6turn0search2
- **Recording Mode:** Any mode that creates/refreshes cassettes. **MUST run serially** (no parallel workers). fileciteturn0file2
- **Tiers:** Tier1=unit, Tier2=integration (UCS replay), Tier3=live (“live spec”). fileciteturn0file3

## R1 — Performance
**Goal:** <10 min full suite; <3 min PR; <3 min quick.  
**Acceptance:**
1. Full suite wall‑clock <10 min in CI.
2. PR pipeline <3 min (Tier1+Tier2 only).
3. Quick mode <3 min (critical path set).  
4. If exceeded, system emits per‑test timings, cassette hit/miss, parallel efficiency. fileciteturn0file2

## R2 — Determinism & Stability
**Acceptance:**
1. Replays are bit‑for‑bit deterministic for request matchers (method, URI, headers, body).  
2. Sanitization removes secrets (auth headers, API keys, PII) **before** write.  
3. Staleness detection via prompt/content hash triggers re‑record pathways.  
4. Clear indicators when re‑recording is required. fileciteturn0file2

## R3 — Coverage & Tiering
**Acceptance:**
1. Maintain ≥92% workflow‑tool coverage overall.  
2. Preserve golden‑path tests as Tier3 (live).  
3. Migrate **80–90%** to Tier2 UCS replay.  
4. Provide explicit markers & strategies per tier. fileciteturn0file2

## R4 — Parallelization (Playback) & Serial (Recording)
**Acceptance:**
1. When enabled, pytest‑xdist runs tests in parallel across workers.  
2. Enforce process isolation (per‑worker storage/paths).  
3. **Recording disables parallelization** automatically (force serial).  
4. Fallback to serial with clear error reporting on parallel failures. fileciteturn0file2  
**Note:** Workflow continuity uses `@pytest.mark.xdist_group` and `--dist loadgroup` to keep a workflow on one worker. citeturn0search0turn0search15

## R5 — Cassette Lifecycle
**Acceptance:**
1. Deterministic cassette names (test/tool/model).  
2. Staleness detection via content hash; auto refresh scheduling.  
3. Monthly automated refresh (configurable).  
4. Scripts/commands to re‑record by test/tool/model. fileciteturn0file2

## R6 — Execution Modes & Markers
**Acceptance:**
1. Markers: `tier1`, `tier2`, `tier3`, `quick`; CLI presets for **quick**, **pr**, **nightly**.  
2. Quick mode runs 6 curated critical‑path tests.  
3. PR runs Tier1+Tier2 only.  
4. Nightly runs all tiers including live.  
5. Custom markers are **registered** to avoid UnknownMark warnings. fileciteturn0file2 citeturn1search0turn1search1turn1search7

## R7 — Maintainability (Deduplication)
**Acceptance:**
1. Reduce duplication by ≥40% via shared abstractions.  
2. Introduce `WorkflowTestRunner` with continuation handling.  
3. Parameterize repetitive tests.  
4. Extract 12 validators + 8 fixtures. fileciteturn0file2

## R8 — Security
**Acceptance:**
1. Pre‑commit + CI gates scan UCS files for secrets.  
2. Sanitization passes must run before write.  
3. Clear remediation output when violations are found. fileciteturn0file2

## R9 — Live Spec Preservation
**Acceptance:**
1. Keep one golden path per workflow tool as live tests.  
2. Preserve model‑specific live validations (e.g., o3/openrouter).  
3. Preserve cross‑tool continuation live coverage.  
4. Run all 6 “quick” tests live in nightly. fileciteturn0file2 fileciteturn0file3

## R10 — Documentation & Tooling
**Acceptance:**
1. Comprehensive docs for UCS, runner, and modes.  
2. Troubleshooting guides for cassette and backend activation.  
3. `make` targets: `test-quick`, `test-pr`, `test-nightly`.  
4. Scripts for re‑record & maintenance. fileciteturn0file2

## R11 — HTTP Client Coverage (UCS)
The system **must** support: requests, httpx, aiohttp. Canonical backends: **responses**/**requests‑mock** (requests), **respx** (httpx), **aioresponses** (aiohttp). citeturn0search18turn0search3turn0search1turn0search2

## R12 — Traceability to faster_sim.md
- Three‑tier plan, live‑spec preservation, cassette determinism, parallelization, modes, and quick‑test set map 1:1 to faster_sim’s goals and examples. Completion of Tasks 1–14 (with serial‑recording & requests‑backend fixes) satisfies the spec. fileciteturn0file3 fileciteturn0file0
