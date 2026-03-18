# TODOs

## Handler Test Coverage
- **What:** Add tests for remaining browse handlers (search, ask, map, collections, tags, pin, readlist)
- **Why:** browse.py has 30+ handlers, current PR covers only 12 critical paths. Remaining handlers have 0 test coverage.
- **Context:** Mock factories from this PR (make_callback, make_message in conftest.py) can be reused directly.
- **Depends on:** Test infrastructure in place (conftest.py mock factories)
