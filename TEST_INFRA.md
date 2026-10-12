# E2E Test Infra: Rewards Farmer Textual TUI Redesign

## Test Philosophy
- **Requirement-Driven & Opaque-Box**: Exercises the user-facing Textual application interface as an end user interacts with it (clicking controls, changing selections, verifying rendered widget content and terminal layout).
- **Subprocess Isolation**: Does not invoke real browsers or live external selenium drivers during automated pilot testing; mocks runtime subprocess boundaries to maintain 100% test repeatability and fast execution (<15 seconds).
- **Zero Regression**: Guarantees all 277 baseline tests pass without regression while adding comprehensive async pilot test coverage.
- **Methodology**: 4-Tier test architecture:
  - Tier 1: Feature Coverage (profile select, task checkboxes, points counter, step progress bar, countdowns)
  - Tier 2: Boundary & Corner Cases (empty profiles, all tasks disabled, max/zero points, terminal resize extremes)
  - Tier 3: Cross-Feature Combinations (switching profile while toggling tasks, points update while running, dynamic resize during run)
  - Tier 4: Real-World Application Scenarios (complete simulated farming session with selective tasks, points accumulation, and window scheduling)

## Feature Inventory
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|---------------------|:------:|:------:|:------:|:------:|
| 1 | Profile Selector UI & Detection | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Profile Env Propagation | ORIGINAL_REQUEST §R1, R4 | 5 | 5 | ✓ | ✓ |
| 3 | Task Toggle Controls | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | Task Filtering Execution | ORIGINAL_REQUEST §R1, R4 | 5 | 5 | ✓ | ✓ |
| 5 | Real-Time Points Counter | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 6 | Points Tracking Backend | ORIGINAL_REQUEST §R2, R4 | 5 | 5 | ✓ | ✓ |
| 7 | Active Step Progress & Details | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 8 | Countdown Timers | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 9 | Countdown Backend Logic | ORIGINAL_REQUEST §R2, R4 | 5 | 5 | ✓ | ✓ |
| 10 | Visual Polish & Containers | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 11 | Responsive Layout (100x40 & 80x24) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 12 | Backward Compatibility | ORIGINAL_REQUEST §Verification | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Test Runner Command**:
  ```powershell
  .venv\Scripts\python.exe -B -m unittest discover -s tests
  ```
- **TUI Pilot Test Suite**:
  ```powershell
  .venv\Scripts\python.exe -B -m unittest tests/test_launcher_tui.py
  ```
- **Harness & Framework**:
  - `unittest.IsolatedAsyncioTestCase` with Textual 7.5.0 pilot (`async with app.run_test(size=(W, H)) as pilot:`).
  - Mocking via `unittest.mock.patch` for `launcher_runtime` and `accounts.list_edge_profiles`.
  - Non-blocking event loop assertions with `await pilot.pause()`.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Multi-profile selection and task subset execution | F1, F2, F3, F4, F12 | Medium |
| 2 | Live session metrics accumulation with search quota progression | F5, F6, F7, F8, F9 | High |
| 3 | Dynamic terminal resize transition (100x40 -> 80x24 -> 120x50) while actively running | F7, F10, F11, F12 | High |
| 4 | Zero tasks enabled prevention and safety recovery | F3, F4, F10, F12 | Medium |
| 5 | Full simulated run lifecycle with points, step indicators, and countdown timers | F1-F12 | High |

## Coverage Thresholds
- Baseline test pass: 277 / 277 tests (0 failures, 0 errors, 7 skipped).
- New pilot test suite in `tests/test_launcher_tui.py`: comprehensive tests covering Tiers 1-4.
- Total test count: >= 284 tests passing.
