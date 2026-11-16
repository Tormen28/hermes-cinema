"""El pane es inglés por defecto y el español es una opción (Playwright + Chrome).

Cierra lo que la segunda revisión dejó como recomendado: nada de español suelto en la interfaz
inglesa y avisos con el tono correcto en ambos idiomas (antes el tono se adivinaba con una regex
en español, así que en inglés todo salía «info»).

Mismas variables que pane_ui_e2e.py (VE_HARNESS, VE_SVC, VE_TOKEN, VE_MEDIA, VE_CHROME)."""
import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pane_ui_e2e as base  # noqa: E402
from pane_ui_e2e import call, check, make_project, CREATED, RESULTS, HARNESS, SVC, CHROME  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SPANISH = re.compile(
    r"[áéíóúñ¿¡]|\b(sin|todav[ií]a|hace|ahora|lista|falta|mudo|sonido|archivos?|escenas?|suena|fondo|"
    r"durante|guardad[oa]|importad[oa]s?|disponible|proyecto|carpeta|guardar|exportar|deshacer)\b",
    re.I,
)


def open_lang(p, pid, lang):
    b = p.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
    pg = b.new_context(viewport={'width': 1280, 'height': 800}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(f'{HARNESS}/harness/index.html?svc={SVC}&open={pid}&lang={lang}')
    pg.wait_for_selector('.ve-clip', timeout=20000)
    pg.wait_for_timeout(600)
    return b, pg, errs


def visible_text(pg):
    return pg.locator('.ve-root').inner_text()


def spanish_words(text):
    return sorted({m.group(0).lower() for m in SPANISH.finditer(text)})


def main():
    if not base.MEDIA:
        sys.exit('define VE_MEDIA con la carpeta de clips de prueba')
    with sync_playwright() as p:
        try:
            pid = make_project('i18n')
            # --- inglés (por defecto): ninguna palabra en español en ninguna pestaña ---
            b, pg, errs = open_lang(p, pid, 'en')
            seen = []
            for tab in ('Scene', 'Effects', 'Audio', 'Project'):
                btn = pg.get_by_role('tab', name=re.compile(tab, re.I))
                if btn.count():
                    btn.first.click(); pg.wait_for_timeout(250)
                seen += spanish_words(visible_text(pg))
            check('I1 interfaz inglesa sin español en las cuatro pestañas', not seen, str(sorted(set(seen))))
            pg.get_by_role('tab', name=re.compile('Scene', re.I)).first.click(); pg.wait_for_timeout(250)
            pg.locator('.ve-clip').first.click(); pg.wait_for_timeout(200)
            ta = pg.locator('textarea').first
            ta.click(); ta.press('Control+a'); ta.type('i18n', delay=20); pg.wait_for_timeout(500)
            pg.keyboard.press('Control+s'); pg.wait_for_timeout(900)
            toast = pg.locator('.ve-toast')
            check('I2 al guardar sale el aviso «Saved» con tono ok (en inglés)',
                  toast.count() == 1 and 've-toast--ok' in (toast.first.get_attribute('class') or '') and 'Saved' in toast.first.inner_text(),
                  toast.first.get_attribute('class') if toast.count() else 'sin aviso')
            pg.wait_for_timeout(2600)
            check('I3 el aviso breve de guardado se va solo (~2 s)', pg.locator('.ve-toast').count() == 0)
            pg.get_by_role('button', name=re.compile('^Export', re.I)).first.click(); pg.wait_for_timeout(500)
            dlg = pg.get_by_role('dialog')
            check('I4 diálogo de exportar en inglés', dlg.count() == 1 and not spanish_words(dlg.inner_text()), str(spanish_words(dlg.inner_text())) if dlg.count() else 'sin diálogo')
            pg.keyboard.press('Escape')
            check('I5 sin errores de página (en)', not errs, str(errs))
            b.close()
            # --- español: sigue disponible y con el mismo tono ---
            b, pg, errs = open_lang(p, pid, 'es')
            pg.locator('.ve-clip').first.click(); pg.wait_for_timeout(200)
            ta = pg.locator('textarea').first
            ta.click(); ta.press('Control+a'); ta.type('es', delay=20); pg.wait_for_timeout(500)
            pg.keyboard.press('Control+s'); pg.wait_for_timeout(900)
            toast = pg.locator('.ve-toast')
            check('I6 en español: «Guardado» con tono ok',
                  toast.count() == 1 and 've-toast--ok' in (toast.first.get_attribute('class') or '') and 'Guardado' in toast.first.inner_text())
            check('I7 en español la interfaz sigue en español', len(spanish_words(visible_text(pg))) >= 3)
            check('I8 sin errores de página (es)', not errs, str(errs))
            b.close()
        finally:
            for pid in CREATED:
                call('DELETE', f'/projects/{pid}')
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} correctas")
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
