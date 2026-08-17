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

    def test_auto_dia_5_a_11_es_bbva05(self):
        assert bot.calcular_tarjeta(datetime.date(2026, 5, 5)) == "BBVA05"
        assert bot.calcular_tarjeta(datetime.date(2026, 5, 11)) == "BBVA05"

    def test_auto_resto_es_bbva12(self):
        assert bot.calcular_tarjeta(datetime.date(2026, 5, 4)) == "BBVA12"
        assert bot.calcular_tarjeta(datetime.date(2026, 5, 12)) == "BBVA12"
        assert bot.calcular_tarjeta(datetime.date(2026, 5, 28)) == "BBVA12"


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
