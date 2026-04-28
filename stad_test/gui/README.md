# Baby Buddy — GUI Test Suite

Selenium-driven browser tests for the Baby Buddy web app. Every test boots a
real Django test server (via pytest-django's `live_server`), launches a Chrome
instance, and drives the app exactly as a human caregiver would — filling
forms, clicking submit buttons, reading the resulting HTML.

## What's in here

| File                                 | Tests | Scope                                            |
| ------------------------------------ | ----- | ------------------------------------------------ |
| `conftest.py`                        | —     | Driver + live-server + user/child fixtures       |
| `test_auth_gui.py`                   | 8     | Login, logout, password reset, user settings     |
| `test_children_gui.py`               | 7     | Add/list/detail child, duplicate-name bug (B-02) |
| `test_tracking_gui.py`               | 10    | Feeding, sleep, diaper, pumping (incl. B-05)     |
| `test_permissions_and_errors_gui.py` | 6     | Anonymous bounce, staff-only gating, 404 (B-01)  |

Total: **31 GUI tests**, four of which are marked `xfail` because they
reproduce live blackbox bugs at the UI layer (B-01, B-02, and two B-05
variants — feeding end-before-start and pumping negative amount).

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
# Headless (default) - fastest, ~45s for all 29 tests
pipenv run pytest stad_test/gui

# Watch the browser drive the app (demo mode)
pipenv run pytest stad_test/gui --headed

# Watch and slow it down so the audience can follow
pipenv run pytest stad_test/gui --headed --slow-gui

# One file at a time
pipenv run pytest stad_test/gui/test_auth_gui.py --headed
```

Expected output on current `main`:

```
============ 27 passed, 4 xfailed in 45.0s ============
```

The three `xfailed` entries are the documented bugs — look at the `XFAIL`
section of the pytest log to see the `reason=` text, which doubles as the
bug report.

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
- **No page-object model.** For 29 tests it adds ceremony without payoff.
  Helpers like `_select_radio_by_value` cover the 3–4 patterns that repeat.
- **`xfail + found_bug` for reproducing bugs.** Same discipline as the
  blackbox suite so CI stays green and `-ra` prints the bug descriptions.
