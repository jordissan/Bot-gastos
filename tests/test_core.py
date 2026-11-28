# Tests de las funciones puras de bot.py — reglas de negocio críticas.
# Correr: .venv/bin/pytest tests/ -v
# No tocan red: solo funciones de parseo, ciclos de tarjeta y categorización por reglas.
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot


# ── Ciclos de tarjeta (docs/REGLAS_NEGOCIO.md) ────────────────────────────────

class TestCalcularTarjeta:
    def test_explicita_gana(self):
        assert bot.calcular_tarjeta(datetime.date(2026, 5, 20), "efvo") == "EFVO"

    def test_auto_sin_tarjeta_por_dia_de_corte(self):
        # Tarjeta por defecto = la que acaba de cortar (Jordi, 25-nov-2026):
        # 5–11 BBVA05 · 12–24 BBVA12 · 25 al 4 HEYB25.
        esperado = {1: "HEYB25", 4: "HEYB25", 5: "BBVA05", 11: "BBVA05",
                    12: "BBVA12", 24: "BBVA12", 25: "HEYB25", 31: "HEYB25"}
        for dia, tarjeta in esperado.items():
            assert bot.calcular_tarjeta(datetime.date(2026, 5, dia)) == tarjeta, dia

    def test_auto_mes_de_pago(self):
        # El Mes sale del corte de la tarjeta elegida.
        d = datetime.date
        assert bot.calcular_mes(d(2026, 11, 3), bot.calcular_tarjeta(d(2026, 11, 3))) == "DIC26"   # HEYB25
        assert bot.calcular_mes(d(2026, 11, 7), bot.calcular_tarjeta(d(2026, 11, 7))) == "DIC26"   # BBVA05
        assert bot.calcular_mes(d(2026, 11, 15), bot.calcular_tarjeta(d(2026, 11, 15))) == "DIC26" # BBVA12
        assert bot.calcular_mes(d(2026, 11, 25), bot.calcular_tarjeta(d(2026, 11, 25))) == "ENE27" # HEYB25


class TestMesActivo:
    """Ciclo activo = ciclo de HEYB25 para hoy: día ≥ 25 → mes+2; antes → mes+1."""

    def _con_hoy(self, monkeypatch, fecha):
        class _DT(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.datetime(fecha.year, fecha.month, fecha.day, 12, 0, tzinfo=tz)
        monkeypatch.setattr(bot.datetime, "datetime", _DT)

    def test_dia_25_salta_dos_meses(self, monkeypatch):
        self._con_hoy(monkeypatch, datetime.date(2026, 11, 25))
        assert bot.mes_activo_str() == "ENE27"

    def test_antes_del_25_es_mes_siguiente(self, monkeypatch):
        self._con_hoy(monkeypatch, datetime.date(2026, 11, 24))
        assert bot.mes_activo_str() == "DIC26"
        self._con_hoy(monkeypatch, datetime.date(2026, 11, 3))
        assert bot.mes_activo_str() == "DIC26"

    def test_dias_en_ciclo_ancla_dia_25(self, monkeypatch):
        self._con_hoy(monkeypatch, datetime.date(2026, 11, 25))
        assert bot._dias_en_ciclo() == 1
        self._con_hoy(monkeypatch, datetime.date(2026, 12, 1))
        assert bot._dias_en_ciclo() == 7  # 25–30 nov (6 días) + 1 dic


class TestCalcularMes:
    def test_bbva05_corte_dia_5(self):
        assert bot.calcular_mes(datetime.date(2026, 5, 4), "BBVA05") == "MAY26"
        assert bot.calcular_mes(datetime.date(2026, 5, 5), "BBVA05") == "JUN26"

    def test_bbva12_corte_dia_12(self):
        assert bot.calcular_mes(datetime.date(2026, 5, 11), "BBVA12") == "MAY26"
        assert bot.calcular_mes(datetime.date(2026, 5, 12), "BBVA12") == "JUN26"

    def test_bmex04_corte_dia_4(self):
        assert bot.calcular_mes(datetime.date(2026, 5, 3), "BMEX04") == "MAY26"
        assert bot.calcular_mes(datetime.date(2026, 5, 4), "BMEX04") == "JUN26"

    def test_heyb25_siempre_al_menos_mes_siguiente(self):
        assert bot.calcular_mes(datetime.date(2026, 5, 24), "HEYB25") == "JUN26"
        assert bot.calcular_mes(datetime.date(2026, 5, 25), "HEYB25") == "JUL26"

    def test_efvo_mes_actual(self):
        assert bot.calcular_mes(datetime.date(2026, 5, 28), "EFVO") == "MAY26"

    def test_cruce_de_anio(self):
        assert bot.calcular_mes(datetime.date(2026, 12, 15), "BBVA12") == "ENE27"
        assert bot.calcular_mes(datetime.date(2026, 12, 26), "HEYB25") == "FEB27"


class TestMesAnterior:
    def test_normal(self):
        assert bot._mes_anterior("JUN26") == "MAY26"

    def test_cruce_de_anio(self):
        assert bot._mes_anterior("ENE26") == "DIC25"


# ── Parseo de mensajes ────────────────────────────────────────────────────────

class TestParsearFecha:
    def test_ayer(self):
        hoy = datetime.datetime.now(datetime.timezone.utc).astimezone().date()
        f, resto = bot.parsear_fecha(["starbucks", "ayer", "150"])
        assert resto == ["starbucks", "150"]
        # ayer en MX puede diferir ±1 día del local; solo validar cercanía
        assert abs((hoy - f).days) <= 2

    def test_sin_fecha_devuelve_hoy_y_tokens_intactos(self):
        f, resto = bot.parsear_fecha(["oxxo", "45"])
        assert resto == ["oxxo", "45"]
        assert isinstance(f, datetime.date)


class TestParsearMensaje:
    def test_formato_estricto(self):
        g = bot.parsear_mensaje("Starbucks 150")
        assert g["concepto"] == "Starbucks"
        assert g["monto"] == 150.0
        assert g["subcategoria"] == "Treat"       # regla: starbucks
        assert g["presupuesto"] == "Diversión"
        assert g["seguro"] is True

    def test_con_tarjeta_explicita(self):
        g = bot.parsear_mensaje("Oxxo 45 BBVA05")
        assert g["tarjeta"] == "BBVA05"
        assert g["subcategoria"] == "Abarrotes"   # regla: oxxo
        assert g["presupuesto"] == "Despensa"

    def test_sin_monto_lanza_valueerror(self):
        try:
            bot.parsear_mensaje("Starbucks")
            assert False, "debió lanzar ValueError"
        except ValueError:
            pass


class TestPareceGastoEstricto:
    def test_gasto_corto_con_numero(self):
        assert bot._parece_gasto_estricto("Oxxo 45") is True

    def test_pregunta_no_es_estricto(self):
        assert bot._parece_gasto_estricto("¿cuánto gasté este mes en abarrotes y restaurantes?") is False


# ── Categorización por reglas (sin red) ───────────────────────────────────────

class TestInferirCategoria:
    def test_regla_starbucks(self):
        assert bot.inferir_categoria("Starbucks Centro") == ("Treat", "Diversión", True)

    def test_regla_gasolina(self):
        assert bot.inferir_categoria("Pemex") == ("Gasolina", "Automovil", True)

    def test_regla_walmart(self):
        assert bot.inferir_categoria("Walmart") == ("Super", "Despensa", True)


class TestGrupoKey:
    def test_match_exacto_con_emoji(self):
        assert bot.grupo_key("🛒 Despensa") == "🛒 Despensa"

    def test_match_sin_emoji(self):
        assert bot.grupo_key("Despensa") == "🛒 Despensa"

    def test_sin_match_devuelve_texto(self):
        assert bot.grupo_key("Agua mineral 70") == "Agua mineral 70"
        assert bot.grupo_key("Agua mineral 70") not in bot.GRUPOS_CAT


# ── Lectura de tarjeta en props Notion (fix v27.1.0) ─────────────────────────

class TestLeerTarjeta:
    def test_prioridad_pago_select(self):
        props = {
            "Pago": {"select": {"name": "BBVA12"}},
            "Estado de Cuenta": {"rich_text": [{"plain_text": "HEYB25"}]},
        }
        assert bot._leer_tarjeta(props) == "BBVA12"

    def test_fallback_estado_de_cuenta(self):
        props = {"Pago": {"select": None},
                 "Estado de Cuenta": {"rich_text": [{"plain_text": "HEYB25"}]}}
        assert bot._leer_tarjeta(props) == "HEYB25"

    def test_fallback_tarjeta_legacy(self):
        props = {"Tarjeta": {"rich_text": [{"plain_text": "EFVO"}]}}
        assert bot._leer_tarjeta(props) == "EFVO"

    def test_vacio(self):
        assert bot._leer_tarjeta({}) == ""


# ── Edición local (base del flujo /corregir y edición contextual) ────────────

class TestEditarGastoLocal:
    BASE = {"concepto": "Oxxo", "monto": 45.0, "fecha": "2026-05-20",
            "tarjeta": "BBVA12", "mes": "JUN26",
            "subcategoria": "Abarrotes", "presupuesto": "Despensa"}

    def test_cambio_monto(self):
        g = bot._editar_gasto_local(self.BASE, {"monto": 95})
        assert g["monto"] == 95.0
        assert g["mes"] == "JUN26"  # sin recálculo

    def test_cambio_tarjeta_recalcula_mes(self):
        g = bot._editar_gasto_local(self.BASE, {"tarjeta": "EFVO"})
        assert g["tarjeta"] == "EFVO"
        assert g["mes"] == "MAY26"  # EFVO = mes calendario

    def test_subcategoria_deriva_presupuesto(self):
        g = bot._editar_gasto_local(self.BASE, {"subcategoria": "Gasolina"})
        assert g["subcategoria"] == "Gasolina"
        assert g["presupuesto"] == "Automovil"  # derivado de SUBCAT_PRESUPUESTO

    def test_no_muta_base(self):
        base = dict(self.BASE)
        bot._editar_gasto_local(base, {"monto": 999})
        assert base["monto"] == 45.0


class TestConstruirPropsEdicion:
    BASE = TestEditarGastoLocal.BASE

    def test_solo_cambios_en_props(self):
        g = dict(self.BASE); g["monto"] = 95.0
        props = bot._construir_props_edicion(self.BASE, g)
        assert set(props) == {"Monto"}
        assert props["Monto"] == {"number": 95.0}

    def test_sin_cambios_props_vacio(self):
        assert bot._construir_props_edicion(self.BASE, dict(self.BASE)) == {}


# ── Formato ──────────────────────────────────────────────────────────────────

class TestFechaCompacta:
    def test_formato(self):
        assert bot._fecha_compacta("2026-05-18") == "18/MAY/26"

    def test_vacia(self):
        assert bot._fecha_compacta("") == ""


# ── Nombres ambiguos SC∩PR (bug "Ezra": v28.1.0) ─────────────────────────────

class TestNombresAmbiguos:
    def test_ezra_y_restaurantes_son_ambiguos(self):
        assert "Ezra" in bot.NOMBRES_AMBIGUOS
        assert "Restaurantes" in bot.NOMBRES_AMBIGUOS

    def test_se_calcula_de_la_interseccion_real(self):
        assert bot.NOMBRES_AMBIGUOS == sorted(set(bot.SC) & set(bot.PR))

    def test_los_ambiguos_tienen_ids_distintos(self):
        # Si los IDs coincidieran no habría riesgo; el bug existe porque difieren.
        for nombre in bot.NOMBRES_AMBIGUOS:
            assert bot.SC[nombre] != bot.PR[nombre], f"{nombre} ya no es ambiguo"

    def test_el_prompt_los_lista(self):
        import inspect
        src = inspect.getsource(bot.responder_consulta_groq)
        assert "NOMBRES_AMBIGUOS" in src


# ── Descripción del plan (transparencia v28.1.0) ─────────────────────────────

class TestDescribirPlan:
    def test_modo_legible_sin_guion_bajo(self):
        assert bot._describir_plan({"modo": "promedio_mensual"}) == "promedio mensual"

    def test_incluye_subcategoria_y_meses(self):
        d = bot._describir_plan({"modo": "promedio_mensual", "subcategoria": "Ezra",
                                 "meses": ["AGO26"]})
        assert "promedio mensual" in d and "Ezra" in d and "AGO26" in d

    def test_historico_gana_sobre_meses(self):
        d = bot._describir_plan({"modo": "detalle", "historico": True, "meses": ["AGO26"]})
        assert "toda la historia" in d and "AGO26" not in d

    def test_plan_vacio_no_revienta(self):
        assert bot._describir_plan({}) == "detalle"


# ── Modelos de Groq (v28.2.0) ────────────────────────────────────────────────
# Groq retiró llama-3.3-70b-versatile y llama-4-scout en agosto/2026: el bot quedó
# inutilizable porque toda clasificación devolvía 404 y caía al parser clásico.

class TestModelosGroq:
    MUERTOS = ("llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct",
               "llama3-70b-8192", "mixtral-8x7b-32768")

    def test_no_se_usan_modelos_retirados(self):
        """Busca solo en literales de código — las menciones en comentarios y
        docstrings son documentación histórica y deben poder quedarse."""
        import ast
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for ruta in ("bot.py", "config.py"):
            tree = ast.parse(open(os.path.join(raiz, ruta)).read())
            docstrings = set()
            for nodo in ast.walk(tree):
                if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    doc = ast.get_docstring(nodo, clean=False)
                    if doc:
                        docstrings.add(doc)
            for nodo in ast.walk(tree):
                if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) \
                        and nodo.value not in docstrings:
                    for muerto in self.MUERTOS:
                        assert muerto not in nodo.value, \
                            f"{ruta}:{nodo.lineno} usa el modelo retirado {muerto}"

    def test_modelos_vienen_de_config_no_hardcodeados(self):
        import inspect
        for fn, const in ((bot.groq_completar, "GROQ_MODELO_TEXTO"),
                          (bot.groq_vision,    "GROQ_MODELO_VISION"),
                          (bot.groq_transcribir, "GROQ_MODELO_AUDIO")):
            src = inspect.getsource(fn)
            assert const in src, f"{fn.__name__} debe usar {const}, no un literal"

    def test_min_tokens_protege_el_razonamiento(self):
        # Con presupuesto corto los modelos de razonamiento devuelven "" en vez de texto.
        assert bot.GROQ_MIN_TOKENS >= 500

    def test_efforts_distintos_por_familia(self):
        # gpt-oss acepta low/medium/high; qwen solo none/default. Mandar el valor
        # equivocado da HTTP 400, por eso son constantes separadas.
        assert bot.GROQ_REASONING_EFFORT != bot.GROQ_VISION_EFFORT


class TestExtraerJsonRazonamiento:
    def test_quita_bloque_think(self):
        crudo = '<think>El usuario {quiere} X</think>\n{"tipo":"consulta"}'
        assert bot._extraer_json(crudo) == {"tipo": "consulta"}

    def test_think_truncado_no_revienta(self):
        assert bot._extraer_json("<think>sin cerrar…") is None

    def test_sigue_soportando_fences(self):
        assert bot._extraer_json('```json\n{"a":1}\n```') == {"a": 1}

    def test_json_pelado(self):
        assert bot._extraer_json('{"a":1}') == {"a": 1}


# ── Orden cronológico de ciclos (v28.2.1) ────────────────────────────────────
# Los códigos MES+AA no se pueden ordenar como texto: alfabéticamente
# "ABR22" < "AGO22" < "DIC25" < "ENE26", que no es el orden real.

class TestCicloOrden:
    def test_ordena_por_fecha_no_alfabeticamente(self):
        meses = ["AGO26", "ABR22", "DIC25", "ENE26", "ABR26"]
        assert sorted(meses, key=bot._ciclo_orden) == ["ABR22", "DIC25", "ENE26", "ABR26", "AGO26"]

    def test_abril_antes_que_agosto_del_mismo_anio(self):
        assert bot._ciclo_orden("ABR26") < bot._ciclo_orden("AGO26")

    def test_cruce_de_anio(self):
        assert bot._ciclo_orden("DIC25") < bot._ciclo_orden("ENE26")

    def test_codigo_invalido_no_revienta(self):
        assert bot._ciclo_orden("XXX") == (0, 0)
        assert bot._ciclo_orden("") == (0, 0)


# ── Cache de meses de Balance (v28.3.2) ───────────────────────────────────────

class TestCacheMeses:
    """Balance tiene 51+ filas: el cache debe leerlas todas (paginado), no solo 50."""

    def _paginas(self, n):
        return [{"id": f"id-{i}", "properties": {"Mes": {"type": "title",
                 "title": [{"plain_text": f"M{i:02d}", "text": {"content": f"M{i:02d}"}}]}}}
                for i in range(n)]

    def test_encuentra_mes_mas_alla_de_50(self, monkeypatch):
        import notion_api
        monkeypatch.setattr(notion_api, "NOTION_BALANCE_ID", "bal")
        monkeypatch.setattr(notion_api, "_meses_cache", {})
        monkeypatch.setattr(notion_api, "query_notion_db", lambda db, f=None: self._paginas(60))
        assert notion_api.buscar_mes_id("M55") == "id-55"

    def test_mes_inexistente_devuelve_none(self, monkeypatch):
        import notion_api
        monkeypatch.setattr(notion_api, "NOTION_BALANCE_ID", "bal")
        monkeypatch.setattr(notion_api, "_meses_cache", {})
        monkeypatch.setattr(notion_api, "query_notion_db", lambda db, f=None: self._paginas(3))
        assert notion_api.buscar_mes_id("ENE27") is None


# ── Presupuestos existentes en Notion (v28.4.1) ──────────────────────────────

class TestPresupuestosValidos:
    """Todo presupuesto al que el bot manda un gasto debe existir en PR (BD Presupuestos).
    Antes, Generosidad/Iglesia/Departamento apuntaban fuera de la BD y esos gastos no sumaban."""

    def test_subcat_presupuesto_existe(self):
        faltan = {s: p for s, p in bot.SUBCAT_PRESUPUESTO.items() if p not in bot.PR}
        assert not faltan, faltan

    def test_reglas_concepto_presupuesto_existe(self):
        faltan = [(sc, p) for _, sc, p in bot.REGLAS_CONCEPTO if p not in bot.PR]
        assert not faltan, faltan

    def test_decisiones_jordi(self):
        sp = bot.SUBCAT_PRESUPUESTO
        assert sp["Diezmo"] == sp["Ofrenda"] == "Diezmo"
        assert sp["Regalos"] == sp["Muebles"] == sp["Decoracion"] == "Personal"
        assert sp["Mercado"] == sp["Comida"] == "Despensa"
        assert bot.PR["Impuestos"].endswith("ad31170d")


# ── Desglose de ticket desplegable (v28.5.0) ─────────────────────────────────

class TestDesgloseTicket:
    G = {"concepto": "Super <Rancherita> & Buga*", "monto": 215.5, "fecha": "2026-11-25",
         "tarjeta": "HEYB25", "mes": "ENE27", "subcategoria": "Abarrotes", "presupuesto": "Despensa"}
    P = [{"nombre": "HUEVO", "precio": 45.88}, {"nombre": "TORTILLA", "precio": 26.04},
         {"nombre": "CILANTRO", "precio": None}, {"nombre": "", "precio": 3}]

    def test_sin_productos_no_hay_desglose(self):
        assert bot._desglose_html([]) == ""
        assert "blockquote" not in bot.msg_gasto_html(self.G)

    def test_cita_desplegable_con_todos(self):
        d = bot._desglose_html(self.P)
        assert "<blockquote expandable>" in d and d.endswith("</blockquote>")
        assert "• HUEVO — $45.88" in d and "• CILANTRO" in d
        assert "(4 artículos)" in d

    def test_escapa_html_y_link(self):
        m = bot.msg_gasto_html(self.G, notion_id="abc-123", productos=self.P)
        assert "Super &lt;Rancherita&gt; &amp; Buga*" in m
        assert '<a href="https://www.notion.so/abc123">🔗 Ver en Notion</a>' in m

    def test_limite(self):
        muchos = [{"nombre": f"P{i}", "precio": 1.0} for i in range(70)]
        d = bot._desglose_html(muchos, limite=60)
        assert "… y 10 más" in d and "• P59" in d and "• P60 " not in d


# ── Comandos en lenguaje natural (v28.7.0) ────────────────────────────────────

class TestComandoNL:
    @staticmethod
    def _det(t):
        return bot.detectar_comando_nl(t)

    def test_frases_que_son_comando(self):
        casos = {
            "Corre una prueba": ("prueba", []),
            "oye bot, corre una prueba porfa": ("prueba", []),
            "quiero hacer una prueba": ("prueba", []),
            "modo prueba": ("prueba", []),
            "haz un diagnóstico": ("diagnostico", []),
            "dame el resumen": ("resumen", []),
            "resumen de JUN26": ("resumen", ["JUN26"]),
            "el top de MAY26": ("top", ["MAY26"]),
            "manda el reporte mensual": ("reporte", ["mensual"]),
            "estadísticas": ("estadisticas", []),
            "quiero corregir un gasto": ("corregir", []),
            "borra el último gasto": ("eliminar", []),
            "busca los gastos de uber": ("buscar", ["uber"]),
            "¿qué puedes hacer?": ("ayuda", []),
            "cancela": ("cancelar", []),
        }
        for frase, esperado in casos.items():
            assert self._det(frase) == esperado, frase

    def test_gastos_y_preguntas_no_son_comando(self):
        for frase in ["Starbucks 150", "gasté 350 en una prueba de covid",
                      "pagué la prueba de laboratorio", "super 350, gasolina 500",
                      "elimina el gasto de uber", "borra los gastos chicos de uber",
                      "corrige el monto a 400", "cámbialo a restaurantes",
                      "¿cuánto gasté en uber?", "Hola", ""]:
            assert self._det(frase) is None, frase

    def test_salir_del_sandbox(self):
        assert bot.es_salida_prueba_nl("sal del modo prueba")
        assert bot.es_salida_prueba_nl("Cancela.")
        assert not bot.es_salida_prueba_nl("Oxxo 45")
        assert not bot.es_salida_prueba_nl("cámbialo a 400")

    def test_prueba_en_palabras_deja_al_usuario_en_el_sandbox(self):
        # Llega por conv_gasto, pero el siguiente mensaje debe caer en conv_prueba.
        import asyncio
        from types import SimpleNamespace
        from telegram.ext import ConversationHandler, CommandHandler

        class Msg:
            def __init__(self): self.enviados = []
            async def reply_text(self, txt, **kw): self.enviados.append(txt)

        uid = next(iter(bot.USUARIOS_AUTORIZADOS))
        msg = Msg()
        update = SimpleNamespace(effective_user=SimpleNamespace(id=uid),
                                 effective_chat=SimpleNamespace(id=uid),
                                 message=msg, effective_message=msg)
        context = SimpleNamespace(user_data={}, args=None)
        conv = ConversationHandler(entry_points=[CommandHandler("prueba", bot.cmd_prueba)],
                                   states={bot.PRUEBA_GASTO: []}, fallbacks=[])
        viejo, bot._conv_prueba = bot._conv_prueba, conv
        viejo_hist, bot.agregar_historial = bot.agregar_historial, lambda *a, **k: None
        try:
            r = asyncio.run(bot.ejecutar_comando_nl(update, context, "prueba", []))
        finally:
            bot._conv_prueba, bot.agregar_historial = viejo, viejo_hist
        assert r == ConversationHandler.END
        assert "Sandbox activado" in msg.enviados[0]
        assert conv._conversations[(uid, uid)] == bot.PRUEBA_GASTO


# ── Tablas de gastos (listados alineados para Telegram) ───────────────────────

class TestTablaGastos:
    ITEMS = [("Temu", 450.69, "2026-11-26"),
             ("Soriana Bugambilias", 429.51, "2026-11-25"),
             ("MERPAGO*ABARROTESBAR", 163, "2026-11-27"),
             ("Super Rancherita Buga", 77, "2026-11-27")]

    def test_renglones_caben_en_iphone(self):
        t = bot._tabla_gastos(self.ITEMS, total=2131.49, n_total=12)
        for linea in t.splitlines():
            assert len(linea) <= bot.TABLA_ANCHO, linea

    def test_columnas_alineadas(self):
        filas = bot._tabla_gastos(self.ITEMS).splitlines()
        assert len({len(f) for f in filas}) == 1          # mismo ancho → montos alineados
        assert filas[0].startswith("26/NOV Temu")
        assert filas[0].endswith("$451")

    def test_total_y_faltantes(self):
        t = bot._tabla_gastos(self.ITEMS, total=2131.49, n_total=12)
        assert "… y 8 más" in t
        assert t.splitlines()[-1].startswith("Total") and t.endswith("$2,131")

    def test_varios_anios_muestra_anio(self):
        t = bot._tabla_gastos([("A", 1, "2025-12-31"), ("B", 2, "2026-01-01")])
        assert t.startswith("31/12/25")

    def test_html_escapa(self):
        h = bot._tabla_html([("A&B <x>", 10, "2026-11-01")])
        assert h.startswith("<pre>") and "A&amp;B &lt;x&gt;" in h

    def test_vacia(self):
        assert bot._tabla_gastos([]) == "" and bot._tabla_html([]) == ""
