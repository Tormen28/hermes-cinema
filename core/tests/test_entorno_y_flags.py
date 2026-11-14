"""Lo que pidió la segunda revisión del catálogo, fijado con pruebas.

Tres cosas concretas:
  * `creationflags` nunca se pasa sin condicionar (en POSIX revienta),
  * el servicio no hereda el entorno de Hermes (ni sus claves),
  * los nombres de toma del skill no llegan crudos a una ruta ni a un shell.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "core"))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("hermes_cinema_pkg", RAIZ / "__init__.py")
paquete = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paquete)  # type: ignore[union-attr]


class TestCreationFlags:
    """`CREATE_NO_WINDOW` solo existe en Windows: pasarlo siempre lanza ValueError."""

    def test_generate_no_pasa_flags_sin_condicionar(self) -> None:
        fuente = (RAIZ / "core" / "service" / "generate.py").read_text(encoding="utf-8")
        sin_condicionar = re.findall(r"creationflags=CREATE_NO_WINDOW,", fuente)
        assert not sin_condicionar, "generate.py pasa CREATE_NO_WINDOW sin condicionar"
        assert 'creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0' in fuente


class TestEntornoHijo:
    """El servicio y sus nietos no pueden ver las claves de proveedor del perfil."""

    def test_no_se_hereda_todo_el_entorno(self) -> None:
        os.environ["SECRETO_DE_PRUEBA"] = "no-debe-pasarse"
        env = paquete.child_env()
        assert "SECRETO_DE_PRUEBA" not in env
        assert set(env) <= set(paquete.ENV_BASE) | set(paquete.ENV_PROVEEDORES)

    def test_las_claves_opcionales_viajan_si_existen(self) -> None:
        original = paquete._get_secret
        try:
            paquete._get_secret = lambda nombre: "clave-de-prueba" if nombre == "VE_GEMINI_KEY" else ""
            env = paquete.child_env()
            assert env.get("VE_GEMINI_KEY") == "clave-de-prueba"
            assert "VE_ELEVEN_KEY" not in env
        finally:
            paquete._get_secret = original

    def test_sin_ambito_no_revienta(self) -> None:
        original = paquete._get_secret
        try:
            paquete._get_secret = lambda nombre: ""
            env = paquete.child_env()
            assert "VE_GEMINI_KEY" not in env
        finally:
            paquete._get_secret = original

    def test_el_manifiesto_declara_las_claves_como_opcionales(self) -> None:
        manifiesto = (RAIZ / "plugin.yaml").read_text(encoding="utf-8")
        assert "optional_env:" in manifiesto
        for clave in ("VE_GEMINI_KEY", "VE_ELEVEN_KEY"):
            assert clave in manifiesto
        # No son obligatorias: nadie debe quedarse fuera por no tenerlas.
        assert "requires_env: []" in manifiesto or "requires_env:" not in manifiesto


class TestNombresDeToma:
    """El nombre sale del script.json del proyecto y acaba en una ruta y en un shell."""

    PATRON = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

    def test_el_script_valida_el_nombre(self) -> None:
        fuente = (RAIZ / "core" / "cinematic" / "scripts" / "tts_say.py").read_text(encoding="utf-8")
        assert "re.fullmatch(" in fuente, "tts_say.py no valida el nombre de la toma"

    def test_acepta_nombres_normales_y_rechaza_inyeccion(self) -> None:
        for bueno in ("T01_open", "T02_journey", "a", "T-1"):
            assert self.PATRON.fullmatch(bueno), bueno
        for malo in ("../fuera", "a b", "a;rm -rf", "a&b", "", "-x", "a" * 65):
            assert not self.PATRON.fullmatch(malo), malo
