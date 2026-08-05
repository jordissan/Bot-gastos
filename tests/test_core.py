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
