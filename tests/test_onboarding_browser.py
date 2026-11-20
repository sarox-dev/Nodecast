"""Optional real-Chromium checks. CI installs Playwright explicitly."""
import os
import socket
import threading
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
import uvicorn
from app import main
from app.services import ai_batch, atomic_extraction, database, raw_storage
from app.services.auth import hash_password

PASSWORD = "Synthetic-browser-passphrase-29"


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as runner:
        try:
            instance = runner.chromium.launch()
        except playwright.Error:
            if os.environ.get("NODECAST_BROWSER_TESTS_REQUIRED"):
                raise
            pytest.skip("Chromium not installed; run playwright install chromium")
        yield instance
        instance.close()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    monkeypatch.setattr(raw_storage, "CONTENTS_DIR", tmp_path)
    monkeypatch.setattr(main, "start_auto_processor", lambda: None)
    monkeypatch.setenv("NODECAST_ACCOUNT_MODE", "shared")
    provider_calls = []
    def forbid_ai(*args, **kwargs):
        provider_calls.append(True)
        raise AssertionError("No AI should be called")
    monkeypatch.setattr(atomic_extraction, "call_provider_model", forbid_ai)
    users = [database.create_user_in_db(name, hash_password(PASSWORD)) for name in ("browser-member", "browser-second")]
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started
    yield f"http://127.0.0.1:{port}", users, provider_calls
    server.should_exit = True
    thread.join(timeout=5)
    listener.close()
    for uid in users:
        ai_batch._status.pop(uid, None)


def login(page, base, username="browser-member"):
    page.goto(base + "/login")
    page.locator("#username").fill(username)
    page.locator("#password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    playwright.expect(page.locator("#onboarding-overlay")).to_be_visible()


def replay(page):
    page.locator("#sidebar-brand-settings").click()
    page.get_by_role("button", name="Replay quick tour").click()
    playwright.expect(page.locator("#onboarding-overlay")).to_be_visible()


def test_dismiss_replay_persistence_focus_and_account_isolation(browser, workspace):
    base, users, _calls = workspace
    context = browser.new_context()
    context.route("https://**/*", lambda route: route.abort())
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    login(page, base)
    playwright.expect(page.get_by_role("button", name="Skip tour", exact=True)).to_be_visible()
    assert page.locator("#page-shell").evaluate("el => el.inert")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.closest('#onboarding-overlay') !== null")
    with page.expect_response(lambda response: response.url.endswith("/api/onboarding") and response.request.method == "PUT") as saved:
        page.get_by_role("button", name="Skip tour", exact=True).click()
    assert saved.value.status == 200
    assert not page.locator("#page-shell").evaluate("el => el.inert")
    # The workspace binds its settings handler after /auth/me resolves. Visible
    # server-rendered controls alone do not mean that initialization has finished.
    # The tour preference request is issued at the end of that initialization.
    with page.expect_response(lambda response: response.url.endswith("/api/onboarding") and response.request.method == "GET"):
        page.reload()
    playwright.expect(page.locator("#query")).to_be_visible()
    assert page.request.get(base + "/api/onboarding").json() == {"dismissed": True}
    playwright.expect(page.locator("#onboarding-overlay")).to_have_count(0)
    replay(page)
    playwright.expect(page.locator("#onboarding-title")).to_have_text("Your knowledge, ready to find again")
    page.keyboard.press("Escape")
    playwright.expect(page.locator("#onboarding-overlay")).to_be_hidden()
    assert page.evaluate("document.activeElement.id") == "sidebar-brand-settings"
    # A separate browser reads the account preference from the server.
    other = browser.new_context()
    other.route("https://**/*", lambda route: route.abort())
    other_page = other.new_page()
    assert other.request.post(base + "/auth/login", data={"username": "browser-member", "password": PASSWORD}).status == 200
    other_page.goto(base)
    playwright.expect(other_page.locator("#query")).to_be_visible()
    assert other.request.get(base + "/api/onboarding").json() == {"dismissed": True}
    playwright.expect(other_page.locator("#onboarding-overlay")).to_have_count(0)
    other.close()
    # A different account on the same browser still gets its own first tour.
    page.request.post(base + "/auth/logout")
    login(page, base, "browser-second")
    assert not errors
    context.close()


@pytest.mark.parametrize("width,height,theme", [(1280, 900, "dark"), (1280, 900, "light"), (375, 812, "dark"), (640, 480, "dark")])
def test_all_tour_steps_fit_and_discord_is_available(browser, workspace, width, height, theme):
    base, _users, _calls = workspace
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
    context.route("https://**/*", lambda route: route.abort())
    context.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page = context.new_page()
    login(page, base)
    for index in range(6):
        playwright.expect(page.locator("#onboarding-count")).to_have_text(f"{index + 1} / 6")
        box = page.locator(".onboarding-panel").bounding_box()
        assert box["x"] >= 0 and box["y"] >= 0
        assert box["x"] + box["width"] <= width + 1
        assert box["y"] + box["height"] <= height + 1
        assert page.locator(".onboarding-panel").evaluate("el => el.scrollWidth <= el.clientWidth")
        if index == 3:
            playwright.expect(page.locator(".onboarding-spotlight")).to_be_visible()
        if index == 5:
            link = page.get_by_role("link", name="Join Nodecast on Discord")
            assert link.get_attribute("href") == "https://discord.gg/tFAM5JST4U"
            assert link.get_attribute("target") == "_blank"
            output = os.environ.get("NODECAST_UI_ARTIFACTS")
            if output:
                Path(output).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(output) / f"tour-{theme}-{width}x{height}.png"))
        page.locator("[data-tour-next]").click()
    playwright.expect(page.locator("#onboarding-overlay")).to_be_hidden()
    page.locator("#sidebar-brand-settings").click()
    playwright.expect(page.get_by_role("link", name="Join Discord")).to_have_attribute("href", "https://discord.gg/tFAM5JST4U")
    context.close()


def test_no_ai_save_search_and_source_in_authenticated_browser(browser, workspace):
    base, users, provider_calls = workspace
    context = browser.new_context()
    context.route("https://**/*", lambda route: route.abort())
    page = context.new_page()
    login(page, base)
    page.get_by_role("button", name="Skip tour", exact=True).click()
    original = "UniqueCheckpointMarker: SQLite WAL checkpoint transfers committed frames to the database file."
    response = page.request.post(base + "/api/capture", data={
        "capture_id": "browser_text_001", "capture_type": "snippet",
        "source": {"url": "https://example.test/sqlite", "title": "SQLite original guide"},
        "anchor": {"selected_text": original},
    })
    assert response.status == 200
    deadline = time.monotonic() + 5
    while not database.get_atomics_by_source(users[0], "browser_text_001") and time.monotonic() < deadline:
        time.sleep(.02)
    assert database.list_ai_providers(users[0]) == []
    page.locator("#search-mode-toggle").click()
    playwright.expect(page.locator("#search-mode-toggle")).to_contain_text("Ask")
    page.locator("#query").fill("UniqueCheckpointMarker")
    page.locator("#query").press("Enter")
    playwright.expect(page.locator("#results-container")).to_contain_text("SQLite original guide")
    playwright.expect(page.locator("#results-container")).to_contain_text("AI is optional")
    link = page.locator('#results-container a[href="https://example.test/sqlite"]').first
    playwright.expect(link).to_be_visible()
    assert page.request.get(base + "/api/capture/browser_text_001").json()["capture"]["anchor"]["selected_text"] == original
    assert provider_calls == []
    context.close()
