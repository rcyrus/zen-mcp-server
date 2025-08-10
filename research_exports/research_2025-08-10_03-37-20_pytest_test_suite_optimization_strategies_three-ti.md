# Research Report: pytest test suite optimization strategies three-tier test pyramid unit integration live API tests

**Generated:** 2025-08-10 03:37:20
**Search Mode:** high
**Max Tokens:** 2000

---

1) Direct Answer
Adopt a three-tier strategy that aligns with the Test Pyramid: make fast, deterministic unit tests the foundation; keep integration tests targeted with reliable, hermetic dependencies (e.g., containers, in-memory/backing services); and run a very small set of live API end-to-end tests behind explicit markers/flags. In pytest, enforce this via markers (unit, integration, live), default deselection of slow/live tests, parallelization and test selection for fast feedback, and strong isolation of I/O to keep the base fast and stable.

2) Key Details
- Structure and selection
  - Markers: Define unit, integration, live and default to running unit + most integration locally; gate live with -m live or an env flag.
  - Selection/caching: Use -k expressions, -m markers, --lf/--ff for last-failed/failed-first to tighten feedback loops.
  - Parallelization: Use pytest-xdist -n auto (or per CI core count) with a suitable scheduler (loadscope/loadfile) for better balancing.

- Test Pyramid ratios and intent
  - Majority small/fast tests, fewer integration, very few end-to-end/live. This reduces flakiness and cost while keeping confidence high.

- Speed and stability levers
  - Fixtures: Prefer function scope by default; session/module scope only where setup is expensive and safe. Avoid autouse for costly fixtures. Minimize global state.
  - I/O isolation: Block outbound network by default in unit/integration via pytest-socket; mock HTTP with respx/responses or record via VCR when appropriate.
  - Databases/services: Use in-memory or containerized dependencies for integration (testcontainers). For Django, reuse_db to skip DB re-creation.
  - Flakiness: Quarantine and/or rerun with pytest-rerunfailures; randomize order with pytest-randomly; add timeouts to catch hangs.
  - Impacted-test runs: Use pytest-testmon to run only tests affected by code changes.
  - CI optimization: Split/partition long suites across workers (pytest-split), fail-fast (--maxfail=1), report slowest tests (--durations), and cache timings to rebalance shards.

- Live API tests
  - Keep a minimal smoke set that exercises real auth, rate limits, error paths. Run on schedule or pre-release, not every PR.
  - Protect with markers and environment checks; add backoff/retries only for the live layer; enforce no-network for all others.

3) Examples
- pytest.ini markers and defaults
  - pytest.ini
    [pytest]
    markers =
      unit: fast, isolated tests; no I/O
      integration: tests with real DB/files/containers; no external network
      live: tests calling real external APIs
    addopts = -m "not live" --durations=10

- Running tiers
  - Local quick pass: pytest -m "unit" -q --lf
  - CI PR job: pytest -m "unit or integration" -n auto --maxfail=1
  - Nightly/live: pytest -m "live" --timeout=30

- Parallel and selection
  - xdist auto parallelism: pytest -n auto --dist=loadfile
  - Re-run only failing then others: pytest --ff
  - Select by name/keyword: pytest -k "serializer and not slow"

- Hermetic HTTP and live gating
  - respx with httpx
    import httpx, respx
    @respx.mock
    def test_fetch_user_unit():
        respx.get("https://api.example.com/users/1").mock(
            return_value=httpx.Response(200, json={"id": 1})
        )
        # call code under test here

  - Block outbound network in non-live tests (conftest.py)
    import os, pytest
    try:
        import pytest_socket
    except ImportError:
        pytest.skip("pytest-socket not installed", allow_module_level=True)

    def pytest_configure(config):
        if "live" not in config.getoption("-m"):
            pytest_socket.disable_socket()

- VCR-style recorded HTTP for integration
  - Using pytest-recording (VCR.py underneath)
    def test_integration_recorded(vcr_cassette_dir):
        # first run hits network, records cassette; later runs replay

- Database/containers for integration
  - pytest-django: reuse test DB
    # pytest.ini
    [pytest]
    addopts = --reuse-db
    # in a test
    @pytest.mark.django_db(transaction=True)
    def test_repo_saves():
        ...

  - testcontainers for services
    from testcontainers.postgres import PostgresContainer
    import psycopg
    def test_integration_db():
        with PostgresContainer("postgres:16") as pg:
            conn = psycopg.connect(pg.get_connection_url())
            # run integration checks

- Live tests marker + env guard
  - Example
    import os, pytest
    live = pytest.mark.live
    @live
    @pytest.mark.skipif(not os.getenv("RUN_LIVE"), reason="Set RUN_LIVE=1 to run live tests")
    def test_real_api_smoke():
        # real HTTP call with requests/httpx

- CI shard balancing and impact-only
  - GitHub Actions sketch
    - name: Install
      run: pip install -U pytest pytest-xdist pytest-split pytest-testmon
    - name: Split tests
      run: echo "PYTEST_ADDOPTS=${{ steps.pytest_split.outputs.pytest_addopts }}" >> $GITHUB_ENV
      id: pytest_split
      uses: jerry-git/pytest-split-action@v3
    - name: Run fast tiers
      run: pytest -m "unit or integration" -n auto --testmon

4) Considerations
- Don’t overuse session-scoped fixtures: they can serialize parallel runs and hide state leaks.
- Prefer mocking/contracts over full live calls: keep the live suite minimal to avoid rate limits, instability, and cost. Consider contract testing (Pact) with provider verification for stronger guarantees than pure stubbing.
- Parametrization explosion: be selective with param values; consider hypothesis with targeted strategies instead of combinatorial grids.
- Flaky test policy: reruns mask issues—pair reruns with quarantines and root-cause work; track flaky rate in CI.
- Security and compliance: never record secrets into VCR cassettes; scrub tokens/IDs and enforce allow-listing recorded hosts.

5) Related Topics
- Contract testing for APIs (Pact)
- Property-based testing for robustness (Hypothesis, Schemathesis for OpenAPI)
- Test impact analysis (pytest-testmon) and historical timing-based splitting (pytest-split)
- Order independence checks (pytest-randomly) and hanging-test detection (pytest-timeout)

Would you like a tailored plan (commands, pytest.ini, CI config) for your repository, including recommended plugin choices and a migration path from your current layout? Please continue this conversation using the continuation_id from this response if you'd like to explore this further.

## Sources

1. [How to use markers](https://docs.pytest.org/en/stable/how-to/mark.html)
2. [Fixtures reference](https://docs.pytest.org/en/stable/how-to/fixtures.html)
3. [Parametrize tests](https://docs.pytest.org/en/stable/how-to/parametrize.html)
4. [Usage and invocation](https://docs.pytest.org/en/stable/usage.html)
5. [pytest-xdist documentation](https://pytest-xdist.readthedocs.io/)
6. [pytest-randomly project](https://github.com/pytest-dev/pytest-randomly)
7. [pytest-timeout on PyPI](https://pypi.org/project/pytest-timeout/)
8. [pytest-rerunfailures on PyPI](https://pypi.org/project/pytest-rerunfailures/)
9. [pytest-socket project](https://github.com/miketheman/pytest-socket)
10. [responses documentation](https://github.com/getsentry/responses)
11. [respx documentation](https://respx.readthedocs.io/)
12. [pytest-recording plugin](https://github.com/kiwicom/pytest-recording)
13. [Schemathesis docs](https://schemathesis.readthedocs.io/)
14. [Hypothesis docs](https://hypothesis.readthedocs.io/)
15. [testcontainers-python docs](https://testcontainers-python.readthedocs.io/)
16. [Reuse the testing database](https://pytest-django.readthedocs.io/en/latest/database.html#reuse-the-testing-database-between-test-runs)
17. [pytest-split GitHub](https://github.com/jerry-git/pytest-split)
18. [pytest-testmon project](https://github.com/tarpas/pytest-testmon)
19. [The Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
20. [Test Sizes](https://testing.googleblog.com/2010/12/test-sizes.html)
21. https://api.example.com/users/1"
