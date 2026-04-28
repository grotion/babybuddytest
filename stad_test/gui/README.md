# Baby Buddy — GUI Test Suite

Selenium-driven browser tests for the Baby Buddy web app. Every test boots a
real Django test server (via pytest-django's `live_server`), launches a Chrome
instance, and drives the app exactly as a human caregiver would — filling
forms, clicking submit buttons, reading the resulting HTML.

## What's in here

| File                                 | Tests | xfail | Scope                                                     |
| ------------------------------------ | ----- | ----- | --------------------------------------------------------- |
| `conftest.py`                        | —     | —     | Driver + live-server + user/child fixtures                |
| `test_auth_gui.py`                   | 8     | 0     | Login, logout, password reset, user settings              |
| `test_children_gui.py`               | 10    | 4     | Add/list/detail child, duplicate-name bug (B-02)          |
| `test_tracking_gui.py`               | 26    | 18    | Feeding, sleep, diaper, pumping (incl. B-05)              |
| `test_permissions_and_errors_gui.py` | 10    | 5     | Anonymous bounce, staff-only gating, 404 (B-01)           |
| `test_updates_gui.py`                | 10    | 1     | Edit-view round-trips for every CRUD resource             |
| `test_timers_gui.py`                 | 6     | 0     | Timer start / stop / restart flows                        |
| `test_api_token_gui.py`              | 3     | 0     | User-settings API token reveal & rotation                 |
| `test_filters_gui.py`                | 7     | 1     | List-page filtering by child / type / method / wet status |
| `test_mobile_gui.py`                 | 4     | 1     | iPhone-13 viewport: no overflow, hamburger, mobile forms  |

Total: **84 GUI test functions** (≈94 collected after parametrization), 30 of
which are marked `xfail` to document live bugs at the UI layer — including
the 404-template syntax error, the duplicate-name slug collision, missing
`MinValueValidator`s on Weight/Feeding/Pumping amounts, and the navbar
hamburger toggle race on Bootstrap 5 under headless Chrome.

## Prerequisites

You need **Google Chrome** (or Chromium) installed on the machine that runs
the tests. `webdriver-manager` auto-downloads a matching ChromeDriver the
first time the suite runs, so there's no manual driver install step.

If you prefer to pre-stage the driver (offline CI, no internet):

```powershell
winget install --id Google.Chrome -e
# then download ChromeDriver from https://chromedriver.chromium.org/
# and drop it somewhere on PATH
```

## Installing the Python deps

The Pipfile already lists `selenium` and `webdriver-manager` under
`[dev-packages]`. A normal `pipenv install --dev` picks them up:

```powershell
cd C:\Users\samso\debug_app\babybuddytest
pipenv install --dev
```

## Running the suite

```powershell
# Headless (default) - all 94 tests run in ~11 minutes end-to-end
pipenv run pytest stad_test/gui

# Watch the browser drive the app (demo mode)
pipenv run pytest stad_test/gui --headed

# Watch and slow it down so the audience can follow
pipenv run pytest stad_test/gui --headed --slow-gui

# One file at a time
pipenv run pytest stad_test/gui/test_auth_gui.py --headed

# Just the new categories (filters / updates / timers / api tokens / mobile)
pipenv run pytest stad_test/gui/test_filters_gui.py stad_test/gui/test_updates_gui.py stad_test/gui/test_timers_gui.py stad_test/gui/test_api_token_gui.py stad_test/gui/test_mobile_gui.py
```

Expected output on current `main`:

```
============ 61 passed, 17 xfailed, 16 xpassed in ~11min ============
```

The 17 `xfailed` entries are documented bugs that still reproduce — look at
the `XFAIL` section of the pytest log to see the `reason=` text, which
doubles as the bug report. The 16 `xpassed` entries are tests that
_used_ to fail and now silently pass; review them to decide whether to
delete the `xfail` marker.

## Notes for the presentation

Slide 9 is the natural place to run `--headed --slow-gui` live. The command
`pipenv run pytest stad_test/gui/test_children_gui.py --headed --slow-gui`
runs in about 15 seconds and includes the "duplicate name" reproduction —
the audience watches Chrome navigate to `/children/add/`, fill a duplicate,
hit submit, and land on a 500 page. Clean, visual, repeatable.

## Troubleshooting

| Symptom                                                                          | Fix                                                                                           |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `SessionNotCreatedException: ... chromedriver ... version`                       | Update Chrome, then delete `%USERPROFILE%\.wdm` and re-run — `webdriver-manager` re-downloads |
| `selenium.common.exceptions.WebDriverException: unknown error: no chrome binary` | Install Chrome via winget (above), or set `$env:GOOGLE_CHROME_SHIM` to the chrome.exe path    |
| `StaleElementReferenceException`                                                 | Usually a race with a redirect. Re-run; if persistent, bump the `wait(driver, 20)` timeout    |
| `AxesBackendRequestParameterRequired`                                            | You're not on `babybuddy.settings.test`. `stad_test/pytest.ini` should pin it as the default  |
| Tests open a visible browser you didn't ask for                                  | Check for a stray `--headed` on your shell history                                            |

## Design choices

- **Function-scoped driver fixture.** A fresh browser per test costs ~200 ms
  of startup but guarantees no cookie / localStorage leakage across tests.
- **Explicit waits only.** No `time.sleep`-based polling except the opt-in
  `--slow-gui` flag. `WebDriverWait` + `expected_conditions` is used at
  every navigation boundary.
- **No page-object model.** For 84 test functions it adds ceremony without
  payoff. Small helpers like `_select_radio_by_value`, `_seed_feeding`, and
  the `set_value` / `check_box` / `click_submit` fixtures in `conftest.py`
  cover the 3–4 form-interaction patterns that actually repeat.
- **`xfail + found_bug` for reproducing bugs.** Same discipline as the
  blackbox suite so CI stays green while still documenting every live bug.
  Each xfailed test's `reason=` field is a self-contained bug report — read
  the pytest log's `XFAIL` section after a run to see the full list.
- **Per-resource update coverage.** `test_updates_gui.py` parametrizes a
  smoke test across every CRUD resource (feeding, sleep, diaper, pumping,
  note, temperature, weight, height) so a regression in URLConf wiring or a
  template include surfaces immediately, not weeks later.
- **Mobile viewport guard.** `test_mobile_gui.py` resizes to iPhone-13 (390 ×
  844 CSS px) after login and asserts that the dashboard doesn't overflow,
  the navbar collapses behind a hamburger, and the child-add form remains
  submittable — the kind of regression CSS refactors quietly break.
