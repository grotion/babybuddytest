# Top-level conftest for the stad_test rootdir.
#
# pytest requires `pytest_addoption` to live in a conftest at or above the
# rootdir (here, stad_test/, where pytest.ini sits).  Subdirectory conftests
# like stad_test/gui/conftest.py see the registered options via
# `request.config.getoption(...)`, but cannot register new ones themselves.


def pytest_addoption(parser):
    """CLI flags for the GUI (Selenium) suite.

    --headed     show the Chromium window instead of running headless
    --slow-gui   add a 0.5s pause after each navigation so the audience can
                 follow along during a live demo
    """
    group = parser.getgroup("gui", "GUI (Selenium) test options")
    group.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run GUI tests with a visible Chromium window (default: headless).",
    )
    group.addoption(
        "--slow-gui",
        action="store_true",
        default=False,
        help="Insert a 0.5s pause after each page load so the audience can follow along.",
    )
