# Simulator Test Optimization Plan

Generated: 2025-08-10

## Executive Summary

This document captures the comprehensive analysis and optimization strategy for the Zen MCP Server simulator test suite. The goal is to reduce test execution time by 75-90% while preserving the test suite's value as a "live specification" for future refactoring.

## Current State Analysis

### Test Suite Metrics

- **Total Test Classes:** 33 active tests
- **Base Classes:** 2 (BaseSimulatorTest, ConversationBaseTest)
- **Workflow Tools Tested:** 11/12 (92% coverage)
- **Execution Time:** 30-45 minutes (full suite)
- **Test Code Volume:** ~10,000 lines with 40% duplication

### Test Architecture Map

```
BaseSimulatorTest (8 tests)
├── Subprocess-based tool calls
├── Log analysis utilities
└── Standalone execution

ConversationBaseTest extends BaseSimulatorTest (25 tests)
├── In-process tool calls
├── Conversation memory preservation
└── Cross-tool continuation support
```

### Workflow Tool Coverage

| Tool | Test Coverage | Test Class |
|------|--------------|------------|
| ✅ analyze | Full | AnalyzeValidationTest |
| ✅ chat | Full | BasicConversationTest, ChatSimpleValidationTest |
| ✅ codereview | Full | CodeReviewValidationTest |
| ✅ consensus | Full | 3 test classes |
| ✅ debug | Full | DebugValidationTest, DebugCertainConfidenceTest |
| ❌ docgen | **GAP** | None |
| ✅ planner | Full | PlannerValidationTest, PlannerContinuationHistoryTest |
| ✅ precommit | Full | PrecommitWorkflowValidationTest |
| ✅ refactor | Full | RefactorValidationTest |
| ✅ secaudit | Full | SecauditValidationTest |
| ✅ testgen | Full | TestGenValidationTest |
| ✅ thinkdeep | Full | ThinkDeepWorkflowValidationTest |

### Cross-Tool Interaction Flows

#### Primary Flow Patterns

1. **Sequential Workflow Chain**

   ```
   chat → thinkdeep → codereview → analyze → debug
   ```

2. **Multi-File Continuation**

   ```
   Tool A (Files 1-3) → Tool B (Files 4-6) → Tool C (Combined)
   ```

3. **Iterative Refinement**

   ```
   Initial Analysis → Deep Investigation → Final Synthesis
   ```

### Critical Path Tests (Quick Mode)

These 6 tests provide maximum coverage in minimal time:

1. **cross_tool_continuation** - Validates memory across tools
2. **conversation_chain_validation** - Core threading validation
3. **consensus_workflow_accurate** - Multi-model consensus
4. **codereview_validation** - Workflow patterns
5. **planner_validation** - Complex planning flows
6. **token_allocation_validation** - Memory management

## Optimization Strategy

### Three-Tier Test Pyramid

```
┌─────────────────────────────┐
│   Tier 3: Live Spec (5%)    │  Real API calls
│   6-8 critical path tests   │  Nightly/Pre-release
├─────────────────────────────┤
│  Tier 2: Integration (75%)  │  VCR.py cassettes
│   Workflow validation        │  PR checks
├─────────────────────────────┤
│    Tier 1: Unit (20%)       │  Pure logic
│    Parsing & validation     │  Every commit
└─────────────────────────────┘
```

### Implementation Phases

#### Phase 1: Foundation (Week 1)

- [ ] Install and configure VCR.py
- [ ] Create WorkflowTestRunner base class
- [ ] Implement cassette sanitization hooks
- [ ] Migrate one test class as proof of concept
- [ ] Define cassette lifecycle policy

#### Phase 2: Migration (Week 2)

- [ ] Convert 80-90% of tests to cassette-based
- [ ] Parameterize repetitive test methods
- [ ] Record golden path cassettes for each tool
- [ ] Implement pytest markers for test tiers
- [ ] Add pre-commit hooks for secret scanning

#### Phase 3: Optimization (Week 3)

- [ ] Enable pytest-xdist parallelization
- [ ] Configure CI pipeline with tier-based execution
- [ ] Implement cassette refresh automation
- [ ] Document developer workflow
- [ ] Create re-record scripts

## Technical Implementation Details

### VCR.py Configuration

```python
# conftest.py
import vcr
import os
import hashlib

def sanitize_request(request):
    """Remove sensitive data from requests"""
    # Sanitize headers
    if 'Authorization' in request.headers:
        request.headers['Authorization'] = 'REDACTED'
    if 'X-API-Key' in request.headers:
        request.headers['X-API-Key'] = 'REDACTED'
    return request

def get_cassette_name(test_name, tool, model):
    """Generate deterministic cassette name"""
    prompt_hash = hashlib.sha256(
        f"{tool}_{model}".encode()
    ).hexdigest()[:8]
    return f"cassettes/{tool}/{test_name}__{model}__{prompt_hash}.yml"

vcr_config = {
    'record_mode': os.getenv('VCR_MODE', 'none'),
    'match_on': ['method', 'uri', 'body'],
    'filter_headers': ['authorization', 'x-api-key'],
    'before_record_request': sanitize_request,
    'decode_compressed_response': True,
}
```

### WorkflowTestRunner Pattern

```python
class WorkflowTestRunner:
    """Abstraction for workflow test patterns"""
    
    def __init__(self, tool_name: str, use_cassette: bool = True):
        self.tool_name = tool_name
        self.use_cassette = use_cassette
        self.steps = []
        self.continuation_id = None
    
    def add_step(self, params: dict, validator: callable):
        """Add a workflow step with validation"""
        self.steps.append((params, validator))
    
    def run(self) -> bool:
        """Execute workflow with automatic continuation"""
        for i, (params, validator) in enumerate(self.steps):
            if self.continuation_id and i > 0:
                params['continuation_id'] = self.continuation_id
            
            response, cont_id = self.call_tool(params)
            if not validator(response):
                return False
            
            self.continuation_id = cont_id
        return True
```

### Test Parameterization Example

```python
@pytest.mark.tier2
@pytest.mark.parametrize("scenario,steps,expected", [
    ("single_session", [...], {...}),
    ("with_continuation", [...], {...}),
    ("complex_plan", [...], {...}),
    ("branching", [...], {...}),
])
def test_planner_scenarios(workflow_runner, scenario, steps, expected):
    """Parameterized planner workflow tests"""
    runner = workflow_runner("planner")
    for step_params, validator in steps:
        runner.add_step(step_params, validator)
    assert runner.run() == expected
```

### CI Pipeline Configuration

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  quick-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run quick tests
        run: pytest -m "quick" -n auto --tb=short
  
  tier1-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run unit tests
        run: pytest -m "tier1" -n auto
  
  tier2-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run integration tests
        run: pytest -m "tier2" -n auto
        env:
          VCR_MODE: none  # Use cassettes only
  
  tier3-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' || github.ref == 'refs/heads/main'
    steps:
      - name: Run live spec tests
        run: pytest -m "tier3" --tb=short
        env:
          VCR_MODE: off  # Real API calls
```

## Risk Mitigation

### Cassette Management

- **Staleness Detection:** Embed prompt hash in cassette metadata
- **Re-record Trigger:** Automated monthly refresh + manual on prompt changes
- **Version Control:** Tag cassettes with model versions

### Security

- **Sanitization:** Multi-layer filtering of sensitive data
- **Pre-commit Hooks:** Scan for secrets before commit
- **CI Gates:** Block PRs with exposed credentials

### Parallelization

- **Process Isolation:** Each pytest-xdist worker gets separate process
- **No Shared State:** InMemoryStorage singleton per process
- **Serial Recording:** Disable parallelization during cassette recording

## Success Metrics

| Metric | Current | Target | Method |
|--------|---------|--------|--------|
| Full Suite Time | 30-45 min | <10 min | Cassettes + Parallelization |
| PR Check Time | 15-20 min | <3 min | Tier 1+2 only |
| Test Code Lines | ~10,000 | ~6,000 | Deduplication |
| Flaky Test Rate | Unknown | 0% | Deterministic cassettes |
| Parallel Efficiency | N/A | 80%+ | Process isolation |

## Migration Checklist

### Week 1

- [ ] Set up VCR.py with sanitization
- [ ] Create WorkflowTestRunner
- [ ] Migrate PlannerValidationTest as POC
- [ ] Document cassette workflow
- [ ] Create re-record script

### Week 2

- [ ] Parameterize workflow tests
- [ ] Record golden path cassettes
- [ ] Add pytest markers
- [ ] Implement quick mode preservation
- [ ] Add security scanning

### Week 3

- [ ] Enable pytest-xdist
- [ ] Configure CI tiers
- [ ] Set up cassette caching
- [ ] Create monitoring dashboard
- [ ] Train team on new workflow

## Preserved "Live Spec" Tests

These tests MUST remain as Tier 3 (real API) tests:

1. **One golden path per workflow tool**
   - planner_validation (main flow)
   - codereview_validation (main flow)
   - debug_validation (main flow)
   - consensus_workflow_accurate
   - thinkdeep_validation (main flow)

2. **Model-specific validation**
   - o3_model_selection
   - openrouter_fallback
   - vertex_ai_models (if using)

3. **Cross-tool continuation**
   - cross_tool_continuation (critical scenarios only)
   - conversation_chain_validation

4. **Quick mode tests**
   - All 6 current quick mode tests

## Developer Workflow

### Running Tests

```bash
# Quick feedback (3 min)
make test-quick

# Full PR validation (10 min)
make test-pr

# Nightly validation (with live APIs)
make test-nightly

# Re-record cassettes
./scripts/re_record.sh --test test_name --model gpt-5
```

### Debugging Failures

1. Check if cassette exists and matches current prompt
2. Review cassette content for obvious issues
3. Re-record if API behavior changed
4. Check logs for detailed error context

## Conclusion

This optimization plan will transform the simulator test suite from a 30-45 minute bottleneck into a <10 minute comprehensive validation suite while preserving its critical value as a "live specification" for the upcoming major refactoring.

The key insight: Separate "proof it works" (Tier 3) from "proof we didn't break it" (Tiers 1-2), enabling both confidence and speed.

## Appendix: Test Duplication Analysis

### Common Patterns Found

- Step-validate-continue: 156 occurrences
- Response parsing: 89 occurrences  
- Continuation ID management: 134 occurrences
- File handling validation: 67 occurrences
- Model selection logic: 45 occurrences

### Deduplication Opportunities

- Extract 12 common validators
- Create 8 shared fixtures
- Parameterize 25 test methods
- Consolidate 15 helper functions

Total estimated code reduction: 40% (4,000 lines)
