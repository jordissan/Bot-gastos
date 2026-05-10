import os
import re
import json
import datetime
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# ─── IDs DE NOTION ───────────────────────────────────────────────────────────
SUBCATEGORIAS = {
    "Super":         "bf7d4b7d",
    "Abarrotes":     "3587eb0cbb9280c5",
    "Carnicería":    "6a734da3d457465db419f195de13909b",
    "Restaurantes":  "1cf748f0639e41469ae2cc73aa86e10a",
    "Gasolina":      "8382b856",
    "Salidas":       "1d87eb0cbb9280c1",
    "Treat":         "1d87eb0cbb9280d5",
    "Luz":           "bf545e8169f840ed",
    "Seguro Auto":   "cf81abcd84824b82",
    "Streaming":     "1d87eb0cbb9280a1",
    "Servicios":     "b4d2856c",
    "Deudas":        "b4d2856c",
    "Renta":         "b4d2856c",
    "MSI":           "b4d2856c",
}

PRESUPUESTOS = {
    "Despensa":          "0e4bbd6e",
    "Diversión":         "a1d0605a",
    "Servicios":         "0a9ef564",
    "Deuda":             "91ab4385",
    "Renta":             "eeb6e041",
    "MSI":               "1fc7eb0cbb92802b",
    "Automóvil":         "20f5ab24",
    "Ezra":              "3547eb0cbb92817b",
    "Restaurantes":      "3547eb0cbb9281e0",
    "Salud":             "3547eb0cbb9281a1ba5dfea0791b8d36",
    "Cuidado personal":  "82916172",
}

# ─── REGLAS DE CATEGORÍA POR CONCEPTO ────────────────────────────────────────
# (concepto_lower, subcategoria, presupuesto)
REGLAS_CONCEPTO = [
    # Supermercados grandes → Super/Despensa
    (["walmart", "soriana", "costco", "bodega aurrera", "sam's"], "Super", "Despensa"),
    # Calii Calii → Super/Despensa (excepción)
    (["calii"], "Super", "Despensa"),
    # Zarapes → Restaurantes/Despensa (excepción)
    (["zarapes"], "Restaurantes", "Despensa"),
    # Carnicerías
    (["carnicería", "carniceria", "carnes especiales", "barranqueño", "barrangueno"], "Carnicería", "Despensa"),
    # Restaurantes
    (["restaurante", "taqueria", "taquería", "tacos", "pizza", "sushi", "pollo", "dq ", "dairy queen",
      "carl's", "carls", "mcdonalds", "mcdonald", "burger", "kfc", "subway", "domino",
      "clip mx*rest", "payclip*rest", "la choco", "chocof", "zarapes"], "Restaurantes", "Restaurantes"),
    # Gasolina
    (["gasolina", "oxxo gas", "oxxogas", "bp ", "petro", "combustible", "gas station"], "Gasolina", "Automóvil"),
    # Streaming
    (["netflix", "spotify", "disney", "hbo", "apple tv", "paramount", "crunchyroll"], "Streaming", "Servicios"),
    # Servicios
    (["izzi", "telmex", "at&t", "att ", "adobe", "icloud", "capcut", "claude", "openai",
      "conekta*parco", "parco"], "Servicios", "Servicios"),
    # Google → Servicios
    (["google"], "Servicios", "Servicios"),
    # Luz
    (["cfe", "luz "], "Luz", "Servicios"),
    # Seguro Auto
    (["mapfre", "seguro", "qualitas", "gnp auto"], "Seguro Auto", "Automóvil"),
    # Farmacias → Salud
    (["farmacia", "farmacias", "benavides", "guadalajara", "ahorro", "similares", "doctor", "médico", "medico", "hospital", "clínica", "clinica"], "Servicios", "Salud"),
    # Abarrotes (todo lo que no sea super grande)
    (["oxxo", "bae ", "naranjitas", "rancherita", "abarrotes", "minisuper", "merpago*abarrotes", "seven"], "Abarrotes", "Despensa"),
    # Salidas/Diversión
    (["cine", "cinema", "teatro", "concierto", "evento", "antro", "bar ", "cerveza", "copas"], "Salidas", "Diversión"),
    # Treat
    (["starbucks", "café", "cafe ", "helado", "nieve", "pastel", "panadería", "panaderia"], "Treat", "Diversión"),
]

# ─── MESES ───────────────────────────────────────────────────────────────────
MESES_ESP = {
    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC"
}

MESES_TEXTO = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

# ─── LÓGICA DE TARJETA Y MES ─────────────────────────────────────────────────
def calcular_tarjeta(fecha: datetime.date, tarjeta_explicita: str = None) -> str:
    if tarjeta_explicita:
        return tarjeta_explicita.upper()
    dia = fecha.day
    if 5 <= dia <= 11:
        return "BBVA05"
    else:
        return "BBVA12"

def calcular_mes(fecha: datetime.date, tarjeta: str) -> str:
    if tarjeta == "BBVA05":
        # Corte día 5: ciclo 5-a-4 → mes de pago = mes siguiente al corte
        if fecha.day >= 5:
            mes_pago = fecha.month + 1
            anio_pago = fecha.year
        else:
            mes_pago = fecha.month
            anio_pago = fecha.year
        if mes_pago > 12:
            mes_pago = 1
            anio_pago += 1
    elif tarjeta == "BBVA12":
        # Corte día 12: ciclo 12-a-11 → mes de pago = mes siguiente al corte
        if fecha.day >= 12:
            mes_pago = fecha.month + 2
            anio_pago = fecha.year
        else:
            mes_pago = fecha.month + 1
            anio_pago = fecha.year
        while mes_pago > 12:
            mes_pago -= 12
            anio_pago += 1
    elif tarjeta == "HEYB25":
        if fecha.day >= 25:
            mes_pago = fecha.month + 2
            anio_pago = fecha.year
        else:
            mes_pago = fecha.month + 1
            anio_pago = fecha.year
        while mes_pago > 12:
            mes_pago -= 12
            anio_pago += 1
    elif tarjeta == "BMEX04":
        if fecha.day >= 4:
            mes_pago = fecha.month + 1
            anio_pago = fecha.year
        else:
            mes_pago = fecha.month
            anio_pago = fecha.year
        if mes_pago > 12:
            mes_pago = 1
            anio_pago += 1
    else:
        mes_pago = fecha.month + 1
        anio_pago = fecha.year
        if mes_pago > 12:
            mes_pago = 1
            anio_pago += 1

    anio_corto = str(anio_pago)[-2:]
    return f"{MESES_ESP[mes_pago]}{anio_corto}"

# ─── LÓGICA DE CATEGORÍA ─────────────────────────────────────────────────────
def inferir_categoria(concepto: str):
    c = concepto.lower()
    for palabras, subcat, presu in REGLAS_CONCEPTO:
        for p in palabras:
            if p in c:
                return subcat, presu
    # Default
    return "Abarrotes", "Despensa"

# ─── PARSEAR FECHA ────────────────────────────────────────────────────────────
def parsear_fecha(tokens: list) -> tuple:
    """Retorna (fecha, tokens_restantes)"""
    hoy = datetime.date.today()
    
    for i, t in enumerate(tokens):
        t_lower = t.lower()
        if t_lower == "ayer":
            return hoy - datetime.timedelta(days=1), tokens[:i] + tokens[i+1:]
        if t_lower == "hoy":
            return hoy, tokens[:i] + tokens[i+1:]
        # formato dd-mm o dd/mm
        match = re.match(r'^(\d{1,2})[-/](\d{1,2})$', t)
        if match:
            dia, mes = int(match.group(1)), int(match.group(2))
            try:
                fecha = datetime.date(hoy.year, mes, dia)
                return fecha, tokens[:i] + tokens[i+1:]
            except:
                pass
        # formato dd-mes (ej: 15-mar)
        match = re.match(r'^(\d{1,2})[-/]([a-z]+)$', t_lower)
        if match:
            dia = int(match.group(1))
            mes_str = match.group(2)
            if mes_str in MESES_TEXTO:
                mes = MESES_TEXTO[mes_str]
                try:
                    fecha = datetime.date(hoy.year, mes, dia)
                    return fecha, tokens[:i] + tokens[i+1:]
                except:
                    pass

    return hoy, tokens

# ─── PARSEAR TARJETA EXPLÍCITA ────────────────────────────────────────────────
def parsear_tarjeta(tokens: list) -> tuple:
    tarjetas_validas = ["BBVA05", "BBVA12", "HEYB25", "BMEX04", "EFVO"]
    for i, t in enumerate(tokens):
        if t.upper() in tarjetas_validas:
            return t.upper(), tokens[:i] + tokens[i+1:]
    return None, tokens

# ─── PARSEAR MONTO ────────────────────────────────────────────────────────────
def parsear_monto(tokens: list) -> tuple:
    for i, t in enumerate(tokens):
        # Limpiar símbolo de peso y comas
        limpio = t.replace("$", "").replace(",", "")
        try:
            monto = float(limpio)
            if monto > 0:
                return monto, tokens[:i] + tokens[i+1:]
        except:
            pass
    return None, tokens

# ─── PARSEAR MENSAJE COMPLETO ─────────────────────────────────────────────────
def parsear_mensaje(texto: str) -> dict:
    tokens = texto.strip().split()
    
    # 1. Extraer fecha
    fecha, tokens = parsear_fecha(tokens)
    
    # 2. Extraer tarjeta explícita
    tarjeta_explicita, tokens = parsear_tarjeta(tokens)
    
    # 3. Extraer monto
    monto, tokens = parsear_monto(tokens)
    
    # 4. Lo que queda es el concepto
    concepto = " ".join(tokens).strip()
    if not concepto:
        raise ValueError("No encontré el concepto del gasto")
    if monto is None:
        raise ValueError("No encontré el monto del gasto")
    
    # 5. Calcular tarjeta y mes
    tarjeta = calcular_tarjeta(fecha, tarjeta_explicita)
    mes = calcular_mes(fecha, tarjeta)
    
    # 6. Inferir categoría
    subcategoria, presupuesto = inferir_categoria(concepto)
    
    return {
        "concepto": concepto.title(),
        "monto": monto,
        "fecha": fecha.strftime("%Y-%m-%d"),
        "tarjeta": tarjeta,
        "mes": mes,
        "subcategoria": subcategoria,
        "presupuesto": presupuesto,
    }

# ─── GUARDAR EN NOTION ────────────────────────────────────────────────────────
def guardar_en_notion(gasto: dict) -> tuple:
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    subcat_id = SUBCATEGORIAS.get(gasto["subcategoria"])
    presu_id  = PRESUPUESTOS.get(gasto["presupuesto"])

    properties = {
        "Concepto": {"title": [{"text": {"content": gasto["concepto"]}}]},
        "Monto":    {"number": gasto["monto"]},
        "Fecha":    {"date": {"start": gasto["fecha"]}},
        "Estado de Cuenta": {"select": {"name": gasto["tarjeta"]}},
        "Mes":      {"select": {"name": gasto["mes"]}},
    }

    if subcat_id:
        properties["Subcategoría"] = {"relation": [{"id": subcat_id}]}
    if presu_id:
        properties["Presupuesto"] = {"relation": [{"id": presu_id}]}

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }

    r = requests.post(url, headers=headers, json=payload)
    return r.status_code == 200, r.text

# ─── HANDLERS DE TELEGRAM ────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *¡Hola! Soy tu bot de gastos.*\n\n"
        "Escríbeme así:\n"
        "`Concepto Monto`\n\n"
        "Ejemplos:\n"
        "`Starbucks 150`\n"
        "`Gasolina 500 BBVA05`\n"
        "`Walmart 350 ayer`\n"
        "`Netflix 299 HEYB25`\n"
        "`Oxxo Gas 400 15-may`\n\n"
        "Tarjetas disponibles: BBVA05, BBVA12, HEYB25, BMEX04, EFVO\n"
        "Si no pones tarjeta, la calculo por la fecha automáticamente 🗓️"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    try:
        gasto = parsear_mensaje(texto)
        guardado, respuesta_notion = guardar_en_notion(gasto)

        if guardado:
            msg = (
                f"✅ *Gasto guardado*\n\n"
                f"📌 *{gasto['concepto']}*\n"
                f"💰 ${gasto['monto']:,.2f}\n"
                f"📅 {gasto['fecha']}\n"
                f"💳 {gasto['tarjeta']}\n"
                f"🗓️ Mes: {gasto['mes']}\n"
                f"🏷️ {gasto['subcategoria']} → {gasto['presupuesto']}"
            )
        else:
            msg = f"⚠️ Se parseó el gasto pero Notion respondió error.\n\n`{respuesta_notion[:200]}`"

        await update.message.reply_text(msg, parse_mode="Markdown")

    except ValueError as e:
        await update.message.reply_text(
            f"❓ {str(e)}\n\nEjemplo: `Starbucks 150` o `Gasolina 500 BBVA05`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error inesperado: {str(e)}",
            parse_mode="Markdown"
        )

# ─── ARRANQUE ────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot de gastos corriendo (sin Claude API)...")
    app.run_polling()

if __name__ == "__main__":
    main()
