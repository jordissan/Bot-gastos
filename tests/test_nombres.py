# Verifica que todo nombre global que bot.py lee exista de verdad en runtime.
#
# Por qué existe: en v28.0.0 se partió bot.py en config.py/notion_api.py usando
# `from X import *`. Ese import NO trae nombres que empiezan con "_", así que
# `_meses_cache` quedó indefinido y TODA consulta en lenguaje natural moría con
# NameError — en silencio, porque no había error handler. `py_compile` no lo
# detecta: NameError es de runtime, no de sintaxis. Este test sí.
import ast
import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot

MODULOS = ["bot.py", "config.py", "notion_api.py"]
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _locales(node):
    """Nombres ligados directamente en el cuerpo de una función (sin descender a anidadas)."""
    out = set()
    for a in ast.walk(node):
        if isinstance(a, ast.arg):
            out.add(a.arg)
        elif isinstance(a, ast.Name) and isinstance(a.ctx, ast.Store):
            out.add(a.id)
        elif isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(a.name)
        elif isinstance(a, ast.ExceptHandler) and a.name:
            out.add(a.name)
        elif isinstance(a, (ast.Import, ast.ImportFrom)):
            for al in a.names:
                out.add(al.asname or al.name.split(".")[0])
    return out


def _nombres_leidos(ruta):
    """{nombre: línea} de los nombres que se leen y no están ligados en ningún
    scope contenedor (por tanto deben resolverse a un global del módulo)."""
    tree = ast.parse(open(ruta).read())
    leidos = {}

    def visitar(node, visibles):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visibles = visibles | _locales(node)   # closures: heredan del padre
        for hijo in ast.iter_child_nodes(node):
            if isinstance(hijo, ast.Name) and isinstance(hijo.ctx, ast.Load):
                if hijo.id not in visibles:
                    leidos.setdefault(hijo.id, hijo.lineno)
            visitar(hijo, visibles)

    visitar(tree, set())
    return leidos


def test_sin_nombres_indefinidos_en_bot():
    faltan = [(n, l) for n, l in sorted(_nombres_leidos(os.path.join(RAIZ, "bot.py")).items())
              if not hasattr(bot, n) and not hasattr(builtins, n)]
    assert not faltan, "Nombres que reventarían en runtime: " + ", ".join(
        f"{n} (bot.py:{l})" for n, l in faltan)


def test_sin_nombres_indefinidos_en_modulos():
    import config, notion_api
    for mod, ruta in ((config, "config.py"), (notion_api, "notion_api.py")):
        faltan = [(n, l) for n, l in sorted(_nombres_leidos(os.path.join(RAIZ, ruta)).items())
                  if not hasattr(mod, n) and not hasattr(builtins, n)]
        assert not faltan, f"{ruta}: " + ", ".join(f"{n}:{l}" for n, l in faltan)


def test_no_hay_star_imports():
    """Los `import *` ciegan a las herramientas de análisis y permitieron el bug
    de v28.0.0. Los imports deben ser explícitos."""
    for ruta in MODULOS:
        tree = ast.parse(open(os.path.join(RAIZ, ruta)).read())
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names):
                raise AssertionError(f"{ruta}:{n.lineno} usa import * — usa imports explícitos")
