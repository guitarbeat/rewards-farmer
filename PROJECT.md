# Project: Rewards Farmer Textual TUI Redesign

## Architecture
Rewards Farmer provides a Textual-based terminal user interface (TUI) for configuring, monitoring, and managing automated Microsoft Rewards farming sessions. The architecture separates concerns across three primary layers:
1. **Presentation Layer (`src/launcher_tui.py`)**: A Textual application (`RewardsFarmerApp`) with a responsive multi-panel layout (configuration panel, live dashboard, step progress display, action buttons, tabbed console log & history). It reacts to state changes via a non-blocking 250ms polling loop and dispatches user actions to the controller.
2. **Controller & Coordination Layer (`src/launcher_controller.py`, `src/launcher_runtime.py`, `src/launcher_progress.py`)**: `LauncherController` owns configuration state (`selected_profile`, `enabled_tasks`), manages child process execution, parses streamed output into progress and metrics (`RunProgress`), and emits immutable state snapshots (`LauncherSnapshot`) to the TUI.
3. **Execution Runtime Layer (`src/sites/ms_rewards/runner.py`, `src/accounts.py`, `src/daily_schedule.py`, `src/main.py`)**: Runs the bot in an unbuffered subprocess, reads environment variables (`REWARDS_EDGE_PROFILES`, `REWARDS_ENABLED_TASKS`), executes enabled task steps, and emits structured log lines (`[STEP]`, `[OK]`, `[SKIP]`, `[FAIL]`, `[DELAY]`, search quotas, and points).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Profile Selection UI & Detection | Select detected Edge profile via TUI dropdown/selector (`#profile-select`) | M2 | ORIGINAL_REQUEST §R1 |
| 2 | Profile Env Propagation | Controller binds selected profile to `REWARDS_EDGE_PROFILES` for bot runtime | M1 | ORIGINAL_REQUEST §R1, R4 |
| 3 | Task Toggle Controls | Interactive checkboxes/toggles for all 6 tasks (Daily Set, Explore, Visual, Misc, Searches, Bonus) | M2 | ORIGINAL_REQUEST §R1 |
| 4 | Task Filtering Execution | Controller passes enabled tasks to runtime; runner skips disabled tasks with `[SKIP]` | M1 | ORIGINAL_REQUEST §R1, R4 |
| 5 | Real-Time Points Counter | Live session points counter widget (`#stat-points`) updating as points are earned | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Points Tracking Backend | Parsing and accumulating points earned in `RunProgress` from quota and task logs | M1 | ORIGINAL_REQUEST §R2, R4 |
| 7 | Active Step Progress & Details | Live active step status label (`#active-step-label`) and ProgressBar (`#active-step-bar`) | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Countdown Timers | Search delay countdown (`#timer-search-delay`) and daily schedule window countdown (`#timer-schedule-window`) | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Countdown Backend Logic | Schedule window remaining calculation and search delay tracking in runtime/controller | M1 | ORIGINAL_REQUEST §R2, R4 |
| 10 | Visual Polish & Containers | Rounded panel borders, status badges, distinct color styling for panels and controls | M2 | ORIGINAL_REQUEST §R3 |
| 11 | Responsive Layout (100x40 & 80x24) | 2-column layout with tabbed content and `@media (max-height: 28)` rules avoiding overflow | M2 | ORIGINAL_REQUEST §R3 |
| 12 | Backward Compatibility | Preserve all existing selectors (`#run`, `#stop`, `#setup`, `#schedule`, `#progress`, `#history`, `#log`, `#status`) and existing test passes | M1, M2, M4 | ORIGINAL_REQUEST §Verification |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Controller & Runtime Backend Sync | Profile detection, task filtering (`REWARDS_ENABLED_TASKS`), points tracking in `RunProgress`, countdown calculations in `launcher_runtime.py`, `launcher_controller.py`, `launcher_progress.py`, and `runner.py` | none | DONE |
| M2 | TUI Redesign & Interactive Controls | Multi-panel layout, Profile Select, Task Checkboxes, Live Dashboard (points, step progress bar, countdowns), TabbedContent, CSS theming, responsive geometry at 100x40 and 80x24 in `src/launcher_tui.py` | M1 | IN_PROGRESS |
| M3 | E2E Testing Suite (Parallel Track) | Comprehensive 4-tier test suite in `tests/test_launcher_tui.py` verifying R1-R4, publishing `TEST_READY.md` | none | PLANNED |
| M4 | Final Integration & E2E Pass | Pass 100% of all tests (baseline 277 + new E2E tests), followed by Tier 5 adversarial hardening | M1, M2, M3 | PLANNED |

## Interface Contracts

### Controller ↔ TUI (`LauncherSnapshot`)
```python
@dataclass
class LauncherSnapshot:
    subtitle: str
    status_text: str
    status_tone: str
    run_count_label: str
    setup_strip: str
    progress_summary: str
    progress_rows: list[progress.StepRow] = field(default_factory=list)
    run_history: list[dict] = field(default_factory=list)
    run_enabled: bool = True
    stop_enabled: bool = False
    run_button_text: str = "Run"
    stopping: bool = False
    preparing_image: bool = False
    running: bool = False
    # Extensions for R1-R4:
    selected_profile: str | None = None
    available_profiles: list[tuple[str, str]] = field(default_factory=list)
    enabled_tasks: dict[str, bool] = field(default_factory=dict)
    points_earned: int = 0
    session_points: int = 0
    active_step: str | None = None
    active_step_detail: str = ""
    search_delay_remaining: float | None = None
    daily_schedule_countdown: str | None = None
```

### Controller ↔ Bot Runtime (Environment Variables)
- `REWARDS_EDGE_PROFILES`: string with selected profile name (e.g. `"Default"`, `"Profile 1"`, or `"all"`).
- `REWARDS_ENABLED_TASKS`: comma-separated string of enabled canonical step names from `AUTOMATION_TASK_STEPS` (e.g. `"Bing daily set,Explore on Bing,Visual search,Misc cards,Required searches,Bonus points"`).

### Bot Runner ↔ Controller (Log Markers)
- `[STEP] <task_name>`: indicates start of step.
- `[OK] <task_name>`: indicates successful completion of step.
- `[SKIP] <task_name>: <reason>`: indicates skipped step (e.g., disabled in configuration).
- `[FAIL] <task_name>: <reason>`: indicates failed step.
- `Search points before: <current>/<max>` & `Search quota complete: <current>/<max>`: updates points and search quota.

## Code Layout
- `src/launcher_tui.py`: Textual application, widget composition, keybindings, responsive CSS.
- `src/launcher_controller.py`: Launcher state controller, subprocess management, environment generation, event polling.
- `src/launcher_runtime.py`: OS preflight checks, profile detection helper, process spawning and termination.
- `src/launcher_progress.py`: Step and points parsing from subprocess log streams.
- `src/sites/ms_rewards/runner.py`: Rewards task executor, task enablement filter.
- `tests/test_launcher_tui.py`: Async Textual pilot test suite.
- `tests/test_launcher.py`: Unit tests for controller, runtime, and progress state.
