# Research Report: pytest-xdist group tests on same worker xdist_group marker workflow continuity

**Generated:** 2025-08-10 04:00:26
**Search Mode:** high
**Max Tokens:** 2000

---

1) Direct Answer
- Use pytest-xdist’s xdist_group marker to force a set of tests to run on the same worker process. This preserves per-worker process state and session/module/class-scoped fixtures across those tests, which is useful for “workflow continuity.”
- Basic usage:
  - Mark each related test with the same group name: @pytest.mark.xdist_group("checkout-flow")
  - Run with xdist: pytest -n auto
- If you don’t want to mark tests individually, you can alternatively group by scope:
  - --dist=loadscope keeps all tests from the same module/class on the same worker.
  - --dist=loadfile keeps all tests from the same file on the same worker.

2) Key Details
- What the marker guarantees:
  - All tests with the same xdist_group value are scheduled to the same worker and will run serially on that worker (like any tests within a single worker process).
  - This helps maintain continuity of per-worker resources (e.g., session-scoped fixtures, caches, authenticated sessions) across those tests.
- What it does not guarantee:
  - xdist_group does not enforce execution order among the grouped tests. If you require a strict sequence, combine with a test ordering mechanism (e.g., pytest-order) or consolidate steps into a single test.
  - It does not guarantee that grouped tests will be executed contiguously with no other tests interleaved on the same worker; they just share the worker.
- Distribution strategies:
  - Default scheduler: --dist=load (work-stealing). Works with xdist_group.
  - Scope-based schedulers: --dist=loadscope or --dist=loadfile automatically group tests by class/module or file without markers.
- Version/markers:
  - Register the marker in pytest.ini to avoid “unknown marker” warnings.
  - Each test should belong to one logical group. Grouping too many tests reduces parallelism and overall speed.

3) Examples
- Basic grouping with the marker:
  - test_checkout.py
    - import pytest
    - @pytest.mark.xdist_group("checkout-flow")
      def test_add_to_cart(...): ...
    - @pytest.mark.xdist_group("checkout-flow")
      def test_apply_coupon(...): ...
    - @pytest.mark.xdist_group("checkout-flow")
      def test_place_order(...): ...
  - Run:
    - pytest -n auto
- Register marker in pytest.ini:
  - [pytest]
    markers =
      xdist_group(name): run tests with the same name on the same xdist worker
- Dynamic grouping during collection (e.g., group by user_id so all variations for a user run on one worker):
  - conftest.py
    - import pytest
    - def pytest_collection_modifyitems(config, items):
        for item in items:
            user_id = item.callspec.params.get("user_id") if hasattr(item, "callspec") else None
            if user_id is not None:
                item.add_marker(pytest.mark.xdist_group(f"user-{user_id}"))
  - test_user_flow.py
    - import pytest
    - @pytest.mark.parametrize("user_id", [101, 102, 103])
      def test_user_workflow(user_id): ...
- Group by file or module instead of markers:
  - Keep each file on a single worker:
    - pytest -n auto --dist=loadfile
  - Keep classes/modules on a single worker:
    - pytest -n auto --dist=loadscope
- Combine with ordering when sequence matters:
  - pip install pytest-order
  - test_checkout.py
    - import pytest
    - @pytest.mark.xdist_group("checkout-flow")
      @pytest.mark.order(1)
      def test_add_to_cart(...): ...
    - @pytest.mark.xdist_group("checkout-flow")
      @pytest.mark.order(2)
      def test_apply_coupon(...): ...
    - @pytest.mark.xdist_group("checkout-flow")
      @pytest.mark.order(3)
      def test_place_order(...): ...
  - Run:
    - pytest -n auto

4) Considerations
- Performance: Big groups serialize more work on a single worker, reducing parallelism. Prefer minimal groups focused on the shared-state need, or consider --dist=loadscope/loadfile if grouping by module/file naturally fits.
- State sharing: Grouping does not share state across workers. It just ensures tests that rely on the same per-worker state/fixtures run in the same process.
- Ordering: If your “workflow continuity” requires strict step order, use a dedicated ordering mechanism (pytest-order) or implement a single end-to-end test that performs all steps.
- Flakiness: If tests pass only when run together on the same worker, make sure hidden inter-test dependencies are intentional. Prefer explicit fixtures over relying on implicit shared state.
- CI reproducibility: Pin pytest/xdist versions in CI to avoid behavior changes, and register custom markers.

5) Related Topics
- Alternative schedulers: --dist=load, --dist=loadscope, --dist=loadfile
- Test ordering: pytest-order, pytest-dependency
- Marker best practices and registration
- Session-scoped fixtures behavior under xdist

Please continue this conversation using the continuation_id from this response if you'd like to explore:
- Which xdist version and scheduler you’re using
- Whether you need strict ordering or just shared-worker continuity
- How big your groups are and whether dynamic grouping during collection would help

## Sources

1. [pytest-xdist documentation – Project overview and usage](https://pytest-xdist.readthedocs.io/en/latest/)
2. [pytest-xdist docs – Distribution strategies: load, loadscope, loadfile](https://pytest-xdist.readthedocs.io/en/latest/distribution.html)
3. [pytest-xdist docs – Grouping tests on the same worker with xdist_group marker](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#grouping-tests-on-the-same-worker)
4. [pytest docs – Registering marks](https://docs.pytest.org/en/stable/how-to/mark.html#registering-marks)
5. [pytest-order plugin documentation](https://pytest-order.readthedocs.io/en/stable/)
6. [Stack Overflow – Run tests grouped on the same worker and ordering considerations](https://stackoverflow.com/questions/76990949/run-pytest-xdist-grouped-tests-on-same-worker-and-in-order)
