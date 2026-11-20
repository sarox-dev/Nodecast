"""Authenticated real-browser acceptance for the shared filter controls."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_onboarding_browser import browser, workspace, login, playwright
from app.services import database


def seed(users, count=2):
    yesterday=(datetime.now(timezone.utc)-timedelta(days=1)).replace(hour=10,minute=0,second=0,microsecond=0).isoformat().replace('+00:00','Z')
    today=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    for index in range(count):
        key=f'filter-github-{index:02}'
        database.insert_capture_ref(users[0],key,'snippet',f'https://github.com/example/{key}',f'GitHub Docker SQLite {index}','GitHub','',yesterday,[],'','')
        database.insert_atomic(users[0],'text','Docker SQLite container setup and recovery.',source_id=key)
    database.insert_capture_ref(users[0],'filter-youtube','video','https://youtube.com/watch?v=synthetic','YouTube Docker SQLite','YouTube','',today,[],'','')
    database.insert_atomic(users[0],'text','Docker SQLite tutorial video.',source_id='filter-youtube')


def start(browser,workspace,**kwargs):
    base,users,calls=workspace
    context=browser.new_context(timezone_id='Europe/Riga',**kwargs)
    context.route('https://**/*',lambda route:route.abort())
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    login(page,base)
    page.get_by_role('button',name='Skip tour',exact=True).click()
    return context,page,base,users,calls,errors


def test_apply_before_typing_cancel_persistence_next_query_clear_and_paging(browser,workspace):
    seed(workspace[1],25)
    context,page,base,users,calls,errors=start(browser,workspace)
    toggle=page.locator('#library-filter-toggle')
    playwright.expect(toggle).to_be_visible()
    assert page.locator('#query').input_value()==''
    toggle.click()
    dialog=page.locator('#library-filters-dialog')
    playwright.expect(dialog).to_be_visible()
    page.locator('#library-filter-sources input[value="github.com"]').check()
    page.locator('#library-filter-period').select_option('last30')
    page.get_by_role('button',name='Apply',exact=True).click()
    playwright.expect(dialog).to_be_hidden()
    playwright.expect(page.locator('#home-filter-chips')).to_contain_text('github.com')
    assert page.locator('#query').input_value()==''
    toggle.click()
    page.locator('#library-filter-period').select_option('today')
    page.get_by_role('button',name='Cancel',exact=True).click()
    playwright.expect(page.locator('#home-filter-chips')).to_contain_text('Last 30 days')
    page.locator('#query').fill('Docker')
    page.locator('#query').press('Enter')
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('20 of 25')
    playwright.expect(page.locator('#saved-browse')).not_to_contain_text('YouTube Docker')
    page.get_by_role('button',name='Load more saved items').click()
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('25 of 25')
    playwright.expect(page.locator('#saved-browse-more')).to_be_hidden()
    with page.expect_popup() as popup:
        page.locator('#saved-browse-items .saved-snapshot-link').first.click()
    saved_text = popup.value
    playwright.expect(saved_text.locator('body')).to_contain_text('Docker SQLite container setup and recovery.')
    saved_text.close()
    page.locator('#workspace-results-query').fill('SQLite')
    page.locator('#workspace-results-query').press('Enter')
    playwright.expect(page.locator('#filter-bar')).to_contain_text('github.com')
    playwright.expect(page.locator('#filter-bar')).to_contain_text('Last 30 days')
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('20 of 25')
    page.reload()
    playwright.expect(page.locator('#library-filter-toggle')).to_have_attribute('aria-label','Filter saved items, 2 active')
    page.locator('#library-filter-toggle').click()
    playwright.expect(page.locator('#library-filter-period')).to_have_value('last30')
    page.get_by_role('button',name='Cancel',exact=True).click()
    page.locator('#query').fill('Docker')
    page.locator('#query').press('Enter')
    page.locator('#filter-bar').get_by_role('button',name='Clear all',exact=True).click()
    playwright.expect(page.locator('#filter-bar')).to_be_hidden()
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('20 of 26')
    assert calls==[] and errors==[]
    context.close()


@pytest.mark.parametrize('theme,width,height',[('dark',1280,900),('light',390,844),('custom',1024,768)])
def test_natural_yesterday_chips_manual_removal_and_filter_dialog_layout(browser,workspace,theme,width,height):
    seed(workspace[1])
    context,page,base,users,calls,errors=start(browser,workspace,viewport={'width':width,'height':height})
    page.evaluate('(theme)=>{localStorage.setItem("theme",theme); document.documentElement.dataset.theme=theme; document.body.dataset.theme=theme;}',theme)
    # Apply through the app's existing theme manager as well.
    page.evaluate('(theme)=>{settingsState.theme=theme; applyTheme();}',theme)
    page.locator('#search-mode-toggle').click()
    page.locator('#query').fill('Parādi visu info par Docker ko saglabāju vakar')
    page.locator('#query').press('Enter')
    playwright.expect(page.locator('#filter-bar')).to_contain_text('Saved: Yesterday')
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('2 of 2')
    page.locator('#filter-bar').get_by_role('button',name='Remove Saved: Yesterday filter',exact=True).click()
    playwright.expect(page.locator('#filter-bar')).to_be_hidden()
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('3 of 3')
    page.locator('#workspace-results-query-form [data-open-library-filters]').click()
    dialog=page.locator('#library-filters-dialog')
    playwright.expect(dialog).to_be_visible()
    page.locator('#library-filter-period').select_option('custom')
    page.locator('#library-filter-start').fill('2026-11-20')
    page.locator('#library-filter-end').fill('2026-11-01')
    page.get_by_role('button',name='Apply',exact=True).click()
    playwright.expect(page.locator('#library-filter-error')).to_be_visible()
    box=dialog.bounding_box()
    assert box['x']>=0 and box['y']>=0 and box['x']+box['width']<=width+1 and box['y']+box['height']<=height+1
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#library-filter-start').fill('2026-11-01')
    page.locator('#library-filter-end').fill('2026-11-20')
    output=os.environ.get('NODECAST_UI_ARTIFACTS')
    if output:
        Path(output).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(Path(output)/f'filters-{theme}-{width}x{height}.png'))
    page.get_by_role('button',name='Apply',exact=True).focus()
    page.keyboard.press('Escape')
    playwright.expect(dialog).to_be_hidden()
    playwright.expect(page.locator('#content-view')).to_be_visible()
    assert calls==[] and errors==[]
    context.close()


def test_filters_only_and_account_isolation(browser,workspace):
    seed(workspace[1])
    context,page,base,users,calls,errors=start(browser,workspace)
    page.locator('#library-filter-toggle').click()
    page.locator('#library-filter-sources input[value="github.com"]').check()
    page.get_by_role('button',name='Apply',exact=True).click()
    page.locator('#query').press('Enter')
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('2 of 2')
    playwright.expect(page.locator('#results-container')).to_contain_text('Filtered saved items')
    playwright.expect(page.locator('#workspace-results-query-form')).to_be_visible()
    page.request.post(base+'/auth/logout')
    page.goto(base+'/login')
    page.locator('#username').fill('browser-second')
    page.locator('#password').fill('Synthetic-browser-passphrase-29')
    page.get_by_role('button',name='Sign in',exact=True).click()
    playwright.expect(page.locator('#onboarding-overlay')).to_be_visible()
    page.get_by_role('button',name='Skip tour',exact=True).click()
    playwright.expect(page.locator('#library-filter-toggle')).to_have_attribute('aria-label','Filter saved items')
    page.locator('#library-filter-toggle').click()
    playwright.expect(page.locator('#library-filter-sources')).not_to_contain_text('github.com')
    assert calls==[] and errors==[]
    context.close()


def test_ai_calendar_filter_becomes_editable_persistent_chips(browser,workspace,monkeypatch):
    from app.services import ai_client
    seed(workspace[1])
    today=datetime.now(timezone.utc).date()
    monday=today-timedelta(days=today.weekday()+7)
    sunday=monday+timedelta(days=6)
    conn=database.get_db(workspace[1][0])
    conn.execute("UPDATE captures SET saved_at=? WHERE source_url LIKE 'https://github.com/%'",(monday.isoformat()+'T10:00:00Z',))
    conn.commit(); conn.close()
    monkeypatch.setattr(database,'get_ai_assignment_for_feature',lambda *_:{'provider_id':'stub','model':'stub'})
    monkeypatch.setattr(database,'get_ai_provider',lambda *_:{'id':'stub'})
    def planner(*_args,**_kwargs):
        import json
        return json.dumps({'filters':{'period':'custom','start_date':monday.isoformat(),'end_date':sunday.isoformat()},'phrases':['ko saglabāju pagājušajā nedēļā']})
    monkeypatch.setattr(ai_client,'call_provider_model',planner)
    context,page,base,users,calls,errors=start(browser,workspace)
    page.locator('#search-mode-toggle').click()
    page.locator('#query').fill('Parādi visu info par Docker ko saglabāju pagājušajā nedēļā')
    page.locator('#query').press('Enter')
    playwright.expect(page.locator('#filter-bar')).to_contain_text(monday.isoformat())
    playwright.expect(page.locator('#filter-bar')).to_contain_text(sunday.isoformat())
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('2 of 2')
    page.locator('#workspace-results-query-form [data-open-library-filters]').click()
    playwright.expect(page.locator('#library-filter-period')).to_have_value('custom')
    playwright.expect(page.locator('#library-filter-start')).to_have_value(monday.isoformat())
    page.get_by_role('button',name='Cancel',exact=True).click()
    page.locator('#workspace-results-query').fill('SQLite')
    page.locator('#workspace-results-query').press('Enter')
    playwright.expect(page.locator('#saved-browse-count')).to_have_text('2 of 2')
    playwright.expect(page.locator('#filter-bar')).to_contain_text(monday.isoformat())
    assert errors==[]
    context.close()
