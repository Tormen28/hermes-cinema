"""Lo que quedó abierto en la segunda revisión del catálogo (recomendado, no bloqueante).

  * el pane no deja texto en español escrito en el código: todo pasa por `t()`, con
    inglés por defecto y español como opción, y `STRINGS.en` / `STRINGS.es` tienen las
    mismas claves;
  * el tono de un aviso (ok / error / info) no se adivina leyendo el texto traducido;
  * `tts_say.py` ya no lanza el comando de voz por un shell.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PLUGIN_JS = RAIZ / "desktop" / "plugin.js"
TTS_SAY = RAIZ / "core" / "cinematic" / "scripts" / "tts_say.py"
sys.path.insert(0, str(RAIZ / "core"))

CLAVE = re.compile(r"^\s+'([A-Za-z0-9_.]+)':", re.M)
LITERAL = re.compile(r"""'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`""")

#: Señales de español en un literal. Sin acentos ni signos, estas palabras no tienen sentido
#: en el código del pane (los nombres de clase, ids y tipos de dato no las contienen).
ESPANOL = re.compile(
    r"[áéíóúñ¿¡]|\b(sin|todav[ií]a|hace|ahora|lista|falta|mudo|sonido|archivos?|escenas?|"
    r"suena|fondo|durante|guardad[oa]|importad[oa]s?|rechaz\w*|inv[aá]lid\w*|fall[oó]|"
    r"disponible|proyecto|carpeta|concedida|pudo|copiar|vista previa)\b",
    re.I,
)


def _partes():
    texto = PLUGIN_JS.read_text(encoding="utf-8")
    i_en = texto.index("\n  en: {")
    i_es = texto.index("\n  es: {")
    fin = texto.index("\n}\n", i_es)
    return texto, texto[i_en:i_es], texto[i_es:fin], (i_en, fin)


def _sin_comentario(linea: str) -> str:
    return re.sub(r"(?<![:'\"`\w])//.*$", "", linea)


class TestTextosDelPane:
    def test_en_y_es_tienen_las_mismas_claves(self) -> None:
        _, en, es, _ = _partes()
        claves_en, claves_es = set(CLAVE.findall(en)), set(CLAVE.findall(es))
        assert claves_en, "no se leyó STRINGS.en"
        assert claves_en - claves_es == set(), f"falta en es: {sorted(claves_en - claves_es)}"
        assert claves_es - claves_en == set(), f"falta en en: {sorted(claves_es - claves_en)}"

    def test_toda_clave_usada_existe(self) -> None:
        texto, en, _, (ini, fin) = _partes()
        fuera = texto[:ini] + texto[fin:]
        usadas = set(re.findall(r"\bt\('([A-Za-z0-9_.]+)'", fuera))
        faltan = usadas - set(CLAVE.findall(en))
        assert faltan == set(), f"t() con clave inexistente: {sorted(faltan)}"

    def test_no_queda_espanol_escrito_en_el_codigo(self) -> None:
        texto, _, _, (ini, fin) = _partes()
        l_ini = texto[:ini].count("\n") + 1
        l_fin = texto[:fin].count("\n") + 1
        hallazgos = []
        for n, linea in enumerate(texto.split("\n"), 1):
            if l_ini <= n <= l_fin:
                continue
            s = linea.strip()
            if s.startswith(("//", "*", "/*")) or "console." in s or s.startswith("keywords:"):
                continue
            for m in LITERAL.finditer(_sin_comentario(linea)):
                lit = next(g for g in m.groups() if g is not None)
                lit = re.sub(r"\$\{[^}]*\}", "", lit)  # lo interpolado es código, no texto
                if ESPANOL.search(lit):
                    hallazgos.append(f"plugin.js:{n}: {lit[:80]!r}")
        assert hallazgos == [], "texto en español fuera de t():\n" + "\n".join(hallazgos)

    def test_el_tono_del_aviso_no_depende_del_idioma(self) -> None:
        texto, *_ = _partes()
        assert "toastTone" not in texto, "el tono se adivinaba leyendo el texto (solo funcionaba en español)"
        assert "noticeState.tone" in texto
        assert "/^Guardado$/" not in texto


class TestTtsSaySinShell:
    @staticmethod
    def _modulo():
        spec = importlib.util.spec_from_file_location("tts_say_sin_shell", TTS_SAY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_el_codigo_no_usa_shell(self) -> None:
        fuente = TTS_SAY.read_text(encoding="utf-8")
        assert "shell=True" not in fuente
        assert ".format(" not in fuente

    def test_argv_con_redireccion_de_entrada(self) -> None:
        mod = self._modulo()
        argv, stdin = mod.build_argv("piper -m v.onnx -f {out} < {txt}", "/tmp/a b/t.txt", "/tmp/o.wav", posix=True)
        assert argv == ["piper", "-m", "v.onnx", "-f", "/tmp/o.wav"]
        assert stdin == "/tmp/a b/t.txt"

    def test_los_metacaracteres_no_se_interpretan(self) -> None:
        mod = self._modulo()
        argv, stdin = mod.build_argv("say -f {txt} -o {out}", "/tmp/a;rm -rf x/t.txt", "/tmp/o$(id).aiff", posix=True)
        assert argv == ["say", "-f", "/tmp/a;rm -rf x/t.txt", "-o", "/tmp/o$(id).aiff"]
        assert stdin is None

    def test_la_voz_de_windows_queda_en_un_solo_argumento(self) -> None:
        from service import cinematic

        mod = self._modulo()
        argv, _ = mod.build_argv(cinematic.VOZ_WINDOWS, r"C:\Users\a b\t.txt", r"C:\Users\a b\o.wav", posix=False)
        assert argv[:3] == ["powershell", "-NoProfile", "-Command"]
        assert len(argv) == 4
        assert r"C:\Users\a b\o.wav" in argv[3] and "{out}" not in argv[3]

    @pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="necesita ffmpeg y ffprobe en el PATH")
    def test_ejecuta_de_verdad_sin_shell(self, tmp_path) -> None:
        """Una toma real: el comando recibe la ruta con espacios y el texto por stdin."""
        proyecto = tmp_path / "pelicula con espacios"
        proyecto.mkdir()
        (proyecto / "script.json").write_text(
            '{"takes":[{"take":"T01_open","lines":[{"spoken":"Hola."}]}]}', encoding="utf-8"
        )
        falso = tmp_path / "tts_falso.py"
        falso.write_text(
            "import sys,subprocess\n"
            "texto = sys.stdin.read()\n"
            "assert 'Hola.' in texto, texto\n"
            "subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=d=0.3','-ar','48000','-ac','1',sys.argv[1]],check=True)\n",
            encoding="utf-8",
        )
        cmd = f'"{sys.executable}" "{falso}" {{out}} < {{txt}}'
        r = subprocess.run(
            [sys.executable, str(TTS_SAY), "--project", str(proyecto), "--cmd", cmd],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert (proyecto / "audio" / "takes" / "T01_open.wav").is_file()


class TestEmparejamientoAntesDeLaPrimeraLlamada:
    def test_el_pane_pide_el_token_antes_de_llamar(self) -> None:
        # Una respuesta sin token no lleva cabeceras CORS: desde la app el pane no podía ni
        # leer su propio 401, así que el emparejamiento «al primer 401» nunca se disparaba.
        texto = PLUGIN_JS.read_text(encoding="utf-8")
        assert "const token = await ensureToken(ctx)" in texto
        assert texto.index("const token = await ensureToken(ctx)") < texto.index("const base = serviceBase(ctx)", texto.index("async function request("))
