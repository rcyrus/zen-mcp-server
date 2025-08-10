# Research Report: respx httpx async testing best practices Python request mocking recording cassettes

**Generated:** 2025-08-10 03:50:41
**Search Mode:** high
**Max Tokens:** 3000

---

1) Direct Answer
- For async HTTP testing with HTTPX, use RESPX (or HTTPX’s MockTransport) to mock requests at the transport layer. This avoids real network I/O, works well with pytest-asyncio, and provides rich request matching and assertions.
- For recording/replaying “cassettes” of real HTTP interactions, use VCR.py with pytest-vcr or pytest-recording. VCR.py supports HTTPX, allowing async tests to run against recorded interactions.

2) Key Details
- RESPX essentials:
  - Use the pytest fixture respx_mock (from RESPX’s pytest plugin) for isolation, and set assert_all_mocked to prevent accidental real network calls.
  - Match on method, URL (host, path), query params, headers, and body using flexible matchers (e.g., params__contains, headers__regex).
  - Configure responses with return_value=httpx.Response(...), side_effect=[...], or side_effect=Exception to simulate errors/timeouts.
  - Pass-through is possible for selective real calls, but keep it disabled by default in unit tests.

- HTTPX MockTransport:
  - Lightweight alternative for unit tests that stub a handler function, used by passing transport=MockTransport(...) to Client/AsyncClient.

- Cassettes with VCR.py:
  - VCR.py supports HTTPX; use record modes (none/new_episodes/once/all) and matchers (method, scheme, host, path, query, body).
  - Sanitize secrets with filter_headers/filter_query_parameters and normalize volatile data with before_record_request/before_record_response.
  - Use pytest-vcr to automatically create and manage cassettes per test with @pytest.mark.vcr or the vcr_cassette_dir fixture.
  - In CI, record_mode="none" to forbid new external calls; locally, prefer "once" or "new_episodes".

3) Examples

- RESPX + pytest-asyncio (function-scoped, no network leaks)
  - Requires: respx, httpx, pytest, pytest-asyncio
  - Using the built-in pytest fixture from RESPX:
    import pytest
    import httpx

    @pytest.mark.asyncio
    async def test_get_user(respx_mock):
        respx_mock.assert_all_mocked = True  # fail on any unmocked network call

        route = respx_mock.get("https://api.example.com/users/123").mock(
            return_value=httpx.Response(200, json={"id": 123, "name": "Ada"})
        )

        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.example.com/users/123")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Ada"
        assert route.called
        assert respx_mock.calls.call_count == 1

- RESPX matchers and error simulation
    # Match query params and headers; simulate a timeout
    respx_mock.get(
        "https://api.example.com/search",
        params__contains={"q": "widgets"},
        headers__contains={"X-Feature": "beta"}
    ).mock(side_effect=httpx.ReadTimeout("read timed out"))

- HTTPX MockTransport (simple handler)
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.host == "api.example.com"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        r = await client.get("https://api.example.com/ping")
        assert r.json() == {"ok": True}

- VCR.py + pytest-vcr with HTTPX (async)
  - Requires: vcrpy, pytest-vcr, httpx, pytest-asyncio
    import pytest
    import httpx

    @pytest.mark.vcr  # cassette stored under tests/cassettes by default
    @pytest.mark.asyncio
    async def test_httpx_with_cassette():
        async with httpx.AsyncClient() as client:
            r = await client.get("https://httpbin.org/json")
        assert r.status_code == 200

  - pytest.ini (recommended)
    [pytest]
    addopts = -q
    filterwarnings = ignore::DeprecationWarning
    vcr_cassette_library_dir = tests/cassettes
    vcr_record_mode = once

  - Optional vcr config (conftest.py)
    import vcr as _vcr

    my_vcr = _vcr.VCR(
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        filter_query_parameters=["token"],
        match_on=["method", "scheme", "host", "port", "path", "query", "body"],
        decode_compressed_response=True,
    )

    def pytest_configure(config):
        # pytest-vcr picks this up if you expose 'vcr' in globals
        global vcr
        vcr = my_vcr

4) Considerations
- Choosing between RESPX vs VCR.py:
  - Use RESPX/MockTransport for unit tests: deterministic, explicit, no external dependencies.
  - Use VCR.py for integration/API-contract tests: capture/lock interactions with real services, then play back.
- Prevent network leakage:
  - With RESPX: assert_all_mocked=True (router/fixture) to fail on unmocked calls.
  - With VCR.py: set record_mode="none" in CI; ensure all expected calls are covered by cassettes.
- Async specifics:
  - Use pytest-asyncio to run async tests. RESPX works with both sync and async HTTPX clients; ensure mocks are active in the same scope as the client call.
- Flakiness and maintenance:
  - Keep cassettes stable by normalizing/removing volatile headers (Date, User-Agent), IDs, and timestamps; otherwise tests can churn.
  - Pin HTTPX versions or adjust VCR matchers if header ordering/encoding changes affect playback.
- Sensitive data:
  - Always filter or redact authorization headers, tokens, set-cookies, and PII in cassettes.
- Alternatives:
  - pytest-httpx provides an httpx_mock fixture similar to RESPX with a slightly different API; pick one library per project to avoid conflicts.

5) Related Topics
- HTTPX transports (ASGITransport for local app testing) and how transports interact with mocking.
- Request libraries parity: responses (requests), aioresponses (aiohttp), pytest-httpx (httpx).
- Contract testing and schema validation alongside recorded cassettes.

Notes on recency and versions:
- RESPX and HTTPX evolve; confirm matcher and API details against the versions in your environment.
- VCR.py’s HTTPX support is version-dependent; ensure you’re on a recent VCR.py release and a current pytest-vcr to avoid missing features. Where behavior differs across versions, prefer using explicit match_on and record_mode settings documented above.

Optional follow-up
- If you’d like, I can produce a minimal, runnable repo scaffold (pytest + pytest-asyncio + RESPX + VCR.py with sensible defaults) tailored to your Python/HTTPX versions. Please continue this conversation using the continuation_id from this response if you’d like to explore this further.

## Sources

1. [RESCX GitHub - lundberg/respx (README)](https://github.com/lundberg/respx)
2. [RESCX Docs - Usage and Pytest plugin](https://lundberg.github.io/respx/)
3. [HTTPX - Advanced: Mock transports](https://www.python-httpx.org/advanced/#mock-transports)
4. [HTTPX - Exceptions](https://www.python-httpx.org/exceptions/)
5. [VCR.py Documentation - Usage](https://vcrpy.readthedocs.io/en/latest/usage.html)
6. [VCR.py Documentation - Configuration](https://vcrpy.readthedocs.io/en/latest/configuration.html)
7. [pytest-vcr - Usage](https://pytest-vcr.readthedocs.io/en/latest/usage.html)
8. [pytest-recording (GitHub)](https://github.com/kiwicom/pytest-recording)
9. [pytest-httpx - Documentation](https://pytest-httpx.readthedocs.io/en/latest/)
10. https://api.example.com/users/123"
11. https://api.example.com/search",
12. https://api.example.com/ping"
13. https://httpbin.org/json"
