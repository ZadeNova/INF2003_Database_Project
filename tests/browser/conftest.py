"""Browser-only fixtures: HTTP through web's runtime role, with no database credentials."""

import pytest

from scripts.sanitize_browser_artifacts import demo_secrets, redact_text, sanitize


def pytest_addoption(parser):
    parser.addoption(
        "--force-browser-failure",
        action="store_true",
        default=False,
        help="Fail the artifact canary deliberately after loading the app.",
    )


@pytest.fixture(scope="session", autouse=True)
def browser_environment(pytestconfig):
    import os

    for name in ("DEMO_CUSTOMER_PASSWORD", "DEMO_SELLER_PASSWORD", "DEMO_OPERATOR_PASSWORD"):
        if not os.environ.get(name):
            raise pytest.UsageError(f"{name} is required; export it without printing the generated value")
    if not pytestconfig.getoption("base_url"):
        raise pytest.UsageError("Pass --base-url for the isolated web service")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1365, "height": 900}}


@pytest.fixture(autouse=True)
def page_timeouts(page):
    page.set_default_timeout(10000)
    page.set_default_navigation_timeout(30000)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.longrepr:
        report.longrepr = redact_text(str(report.longrepr), demo_secrets())


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    # Context teardown has already saved retained traces; sanitize them before they
    # can be uploaded. The workflow repeats this guard before the upload step.
    sanitize(session.config.getoption("output"))
