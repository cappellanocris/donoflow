"""Test end-to-end nel browser (Playwright) per donatore, operatore, admin e smartphone.

Uso, su un database appena creato con i dati demo:
    python manage.py migrate && python manage.py seed_demo
    python manage.py runserver 127.0.0.1:8765        # in un altro terminale
    pip install playwright && playwright install chromium
    python scripts/e2e_browser.py screenshots/

Crea uno screenshot per pagina nella cartella indicata e stampa PASS/FAIL per
ogni controllo. ATTENZIONE: modifica il database (registra un donatore, prenota...).
"""
import re, json, os, sys
from playwright.sync_api import sync_playwright, expect

BASE = 'http://127.0.0.1:8765'

# ID delle prime due raccolte demo (la seconda è quella completamente prenotata).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'donoflow.settings')
import django; django.setup()
from core.models import DonationSession
S1, S2 = DonationSession.objects.order_by('date').values_list('pk', flat=True)[:2]
SHOTS = sys.argv[1] if len(sys.argv) > 1 else 'screenshots'
os.makedirs(SHOTS, exist_ok=True)
log = []
def step(role, name, ok, detail=''):
    log.append((role, name, ok, detail)); print(('PASS ' if ok else 'FAIL ') + f'[{role}] {name}' + (f' | {detail}' if detail else ''))

def instrument(page, role):
    page.on('dialog', lambda d: d.accept())
    page.on('console', lambda m: m.type == 'error' and step(role, 'console error', False, m.text[:160]))
    page.on('pageerror', lambda e: step(role, 'JS error', False, str(e)[:160]))
    page.on('response', lambda r: r.status >= 400 and '/favicon' not in r.url and step(role, f'HTTP {r.status}', False, r.url))

def msg(page):
    el = page.locator('.messages .alert')
    return ' / '.join(el.all_inner_texts()).replace('\n', ' ').strip() if el.count() else ''

def overflow(page):
    return page.evaluate('document.documentElement.scrollWidth > window.innerWidth + 1')

def shot(page, name):
    page.screenshot(path=f'{SHOTS}/{name}.png', full_page=True)

with sync_playwright() as p:
    br = p.chromium.launch()

    # ---------------- DONATORE NUOVO ----------------
    ctx = br.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); instrument(pg, 'donatore')
    pg.goto(BASE + '/'); shot(pg, 'd01_home_anon')
    step('donatore', 'Home mostra prossima raccolta', 'Nessuna raccolta programmata' not in pg.content())
    pg.goto(BASE + '/accounts/register/')
    f = {'username': 'e2e_donor', 'first_name': 'Test', 'last_name': 'Donatore', 'email': 'e2e@example.com', 'phone': '3331234567',
         'password1': 'Pass-e2e-2026!', 'password2': 'Pass-e2e-2026!'}
    for k, v in f.items(): pg.fill(f'#id_{k}', v)
    pg.select_option('#id_preferred_channel', 'EMAIL')
    pg.click('button:has-text("Crea il mio account")'); pg.wait_for_load_state()
    step('donatore', 'Registrazione → dashboard', '/dashboard' in pg.url, pg.url); shot(pg, 'd02_dashboard_new')
    pg.goto(BASE + '/sessions/'); shot(pg, 'd03_sessions')
    n = pg.locator('.session-card').count(); step('donatore', 'Elenco raccolte popolato', n > 0, f'{n} card')
    pg.goto(BASE + f'/sessions/{S1}/'); shot(pg, 'd04_session_detail')
    btn = pg.locator('button:has-text("Prenota")').first
    step('donatore', 'Slot prenotabili visibili', btn.count() > 0)
    btn.click(); pg.wait_for_load_state()
    step('donatore', 'Prenotazione confermata', 'Prenotazione confermata' in msg(pg), msg(pg))
    step('donatore', 'Dashboard mostra la prenotazione', pg.locator('table tbody tr').first.inner_text().count('Confermata') > 0 or 'Confermata' in pg.content())
    shot(pg, 'd05_dashboard_booked')
    # doppia prenotazione nella stessa giornata (bug atteso)
    pg.goto(BASE + f'/sessions/{S1}/'); pg.locator('button:has-text("Prenota")').first.click(); pg.wait_for_load_state()
    step('donatore', 'Blocca seconda prenotazione stessa giornata', 'Prenotazione confermata' not in msg(pg), msg(pg))
    pg.goto(BASE + '/'); step('donatore', 'Home mostra "Prossima donazione" personale', 'Gestisci' in pg.content()); shot(pg, 'd06_home_logged')
    pg.goto(BASE + '/dashboard/'); pg.locator('button:has-text("Annulla")').first.click(); pg.wait_for_load_state()
    step('donatore', 'Annullamento', 'annullata' in msg(pg).lower(), msg(pg))
    pg.goto(BASE + f'/sessions/{S2}/'); shot(pg, 'd07_session_full')
    pg.goto(BASE + f'/sessions/{S2}/waitlist/'); shot(pg, 'd08_waitlist_form')
    pg.click('button:has-text("Inseriscimi in lista")'); pg.wait_for_load_state()
    step('donatore', 'Iscrizione lista d’attesa', 'lista' in msg(pg).lower(), msg(pg))
    pg.goto(BASE + f'/sessions/{S2}/standby/'); pg.fill('#id_max_arrival_minutes', '10')
    pg.click('button:has-text("Conferma standby")'); pg.wait_for_load_state()
    step('donatore', 'Conferma standby', 'standby' in msg(pg).lower(), msg(pg))
    pg.goto(BASE + '/area-personale/'); shot(pg, 'd09_profile')
    pg.fill('#id_phone', '3339999999'); pg.click('button:has-text("Salva modifiche")'); pg.wait_for_load_state()
    step('donatore', 'Modifica profilo', 'aggiornata' in msg(pg).lower(), msg(pg))
    # logout
    pg.locator('.account-button').click(); pg.locator('.dropdown-logout').click(); pg.wait_for_load_state()
    step('donatore', 'Logout', 'Accedi' in pg.content())
    ctx.close()

    # ---------------- OPERATORE / ADMIN ----------------
    ctx = br.new_context(viewport={'width': 1440, 'height': 900}); pg = ctx.new_page(); instrument(pg, 'operatore')
    pg.goto(BASE + '/accounts/login/'); pg.fill('#id_username', 'admin'); pg.fill('#id_password', 'admin12345')
    pg.click('button:has-text("Entra")'); pg.wait_for_load_state()
    step('operatore', 'Login admin → dashboard operatore', '/operator' in pg.url, pg.url); shot(pg, 'o01_operator_dashboard')
    pg.goto(BASE + f'/operator/sessions/{S2}/'); shot(pg, 'o02_console')
    pg.locator('button:has-text("Check-in")').first.click(); pg.wait_for_load_state()
    step('operatore', 'Check-in dalla console', 'Check-in registrato' in msg(pg), msg(pg))
    # menu Altro → ritardo critico sullo slot 2
    pg.locator('.row-menu').nth(1).locator('button:has-text("Altro")').click()
    pg.wait_for_timeout(400); vis = pg.locator('.row-menu').nth(1).locator('.row-menu-panel').is_visible()
    step('operatore', 'Menu "Altro" si apre', vis); shot(pg, 'o03_menu_open')
    pg.locator('.row-menu').nth(1).locator('button:has-text("ritardo critico")').click(); pg.wait_for_load_state()
    step('operatore', 'Segna ritardo critico', 'ritardo critico' in msg(pg), msg(pg))
    pg.locator('.row-menu').nth(1).locator('button:has-text("Altro")').click()
    pg.locator('.row-menu').nth(1).locator('button:has-text("Attiva standby")').click(); pg.wait_for_load_state()
    step('operatore', 'Attiva standby → offerte inviate', 'Offerta urgente inviata' in msg(pg), msg(pg))
    pg.locator('button:has-text("Simula sì")').first.click(); pg.wait_for_load_state()
    step('operatore', 'Simula risposta sì', 'Risposta simulata' in msg(pg), msg(pg))
    pg.locator('button:has-text("Assegna slot")').first.click(); pg.wait_for_load_state()
    step('operatore', 'Assegna sostituto', 'Slot assegnato' in msg(pg), msg(pg)); shot(pg, 'o04_console_after')
    # gestione prenotazioni
    pg.goto(BASE + f'/gestione/raccolte/{S2}/prenotazioni/'); shot(pg, 'o05_management_appointments')
    step('operatore', 'Pannello prenotazioni', pg.locator('table').count() > 0)
    pg.locator('button:has-text("Invia email")').first.click(); pg.wait_for_load_state()
    step('operatore', 'Invio email riepilogo', 'Email' in msg(pg), msg(pg))
    pg.goto(BASE + f'/gestione/raccolte/{S2}/stampa/'); shot(pg, 'o06_print')
    # gestione raccolte
    pg.goto(BASE + '/gestione/raccolte/'); shot(pg, 'o07_management_sessions')
    pg.locator('.row-menu').first.locator('button:has-text("Altro")').click()
    pg.locator('.row-menu').first.locator('a:has-text("Modifica")').click(); pg.wait_for_load_state(); shot(pg, 'o08_session_form')
    valid = pg.evaluate("document.querySelector('#id_date').value")
    step('operatore', 'Campo data precompilato nel modulo di modifica', bool(valid), repr(valid))
    pg.locator('main button:has-text("Salva")').first.click(); pg.wait_for_load_state()
    step('operatore', 'Salvataggio raccolta', 'aggiornata' in msg(pg).lower(), msg(pg))
    # nuova raccolta
    pg.goto(BASE + '/gestione/raccolte/nuova/')
    pg.select_option('#id_center', index=1); pg.fill('#id_title', 'Raccolta E2E'); pg.fill('#id_date', '2026-11-20')
    pg.fill('#id_start_time', '08:00'); pg.fill('#id_end_time', '11:00'); pg.fill('#id_capacity', '10'); pg.fill('#id_public_slots', '8'); pg.fill('#id_reserved_slots', '2')
    pg.click('button:has-text("Salva e genera slot mancanti")'); pg.wait_for_load_state()
    step('operatore', 'Nuova raccolta + slot', 'Slot creati: 10' in msg(pg), msg(pg))
    # sedi, pagine, footer
    pg.goto(BASE + '/gestione/sedi/nuova/'); pg.fill('#id_name', 'Sede E2E'); pg.fill('#id_city', 'Palermo'); pg.locator('main button[type=submit]').first.click(); pg.wait_for_load_state()
    step('operatore', 'Nuova sede', 'creata' in msg(pg), msg(pg)); shot(pg, 'o09_centers')
    pg.goto(BASE + '/gestione/pagine/nuova/'); pg.fill('#id_title', 'Pagina E2E'); pg.fill('#id_slug', 'pagina-e2e'); pg.fill('#id_content', '<p>Ciao</p>')
    pg.locator('main button[type=submit]').first.click(); pg.wait_for_load_state()
    step('operatore', 'Nuova pagina CMS', 'creata' in msg(pg), msg(pg))
    pg.goto(BASE + '/p/pagina-e2e/'); step('operatore', 'Pagina CMS pubblica', 'Ciao' in pg.content())
    pg.goto(BASE + '/gestione/footer/'); shot(pg, 'o10_footer')
    ctx.close()

    # ---------------- MOBILE ----------------
    for role, login in [('mobile-anon', None), ('mobile-donor', ('mario', 'demo12345')), ('mobile-admin', ('admin', 'admin12345'))]:
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); pg = ctx.new_page(); instrument(pg, role)
        if login:
            pg.goto(BASE + '/accounts/login/'); pg.fill('#id_username', login[0]); pg.fill('#id_password', login[1]); pg.click('button:has-text("Entra")'); pg.wait_for_load_state()
        urls = {'mobile-anon': ['/', '/sessions/', f'/sessions/{S1}/', '/come-funziona/', '/accounts/register/'],
                'mobile-donor': ['/dashboard/', '/area-personale/', f'/sessions/{S2}/standby/'],
                'mobile-admin': ['/operator/', f'/operator/sessions/{S2}/', '/gestione/raccolte/', f'/gestione/raccolte/{S2}/prenotazioni/']}[role]
        if role == 'mobile-admin':
            pg.goto(BASE + f'/operator/sessions/{S2}/')
            box = pg.locator('button:has-text("Check-in")').first.bounding_box()
            step(role, 'Check-in raggiungibile senza scroll laterale su smartphone', bool(box) and box['x'] + box['width'] <= 390, box)
        for u in urls:
            pg.goto(BASE + u); o = overflow(pg)
            step(role, f'Nessuno scroll orizzontale {u}', not o)
            shot(pg, f'm_{role}_{u.strip("/").replace("/", "_") or "home"}')
        if role == 'mobile-anon':
            pg.goto(BASE + '/'); pg.click('.mobile-menu-button'); pg.wait_for_timeout(500); step(role, 'Menu mobile si apre', pg.locator('#mobile-navigation').is_visible())
        ctx.close()
    br.close()

json.dump(log, open(f'{SHOTS}/e2e_log.json', 'w'), ensure_ascii=False, indent=1)
fails = [l for l in log if not l[2]]
print(f'\nTOTALE {len(log)} controlli, {len(fails)} falliti')
