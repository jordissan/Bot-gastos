import os
import re
import datetime
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# ─── IDs DE NOTION ───────────────────────────────────────────────────────────
SUBCATEGORIAS = {
    "Super":        "bf7d4b7d",
    "Abarrotes":    "3587eb0cbb9280c5",
    "Carnicería":   "6a734da3d457465db419f195de13909b",
    "Restaurantes": "1cf748f0639e41469ae2cc73aa86e10a",
    "Gasolina":     "8382b856",
    "Salidas":      "1d87eb0cbb9280c1",
    "Treat":        "1d87eb0cbb9280d5",
    "Luz":          "bf545e8169f840ed",
    "Seguro Auto":  "cf81abcd84824b82",
    "Streaming":    "1d87eb0cbb9280a1",
    "Servicios":    "b4d2856c",
}

PRESUPUESTOS = {
    "Despensa":         "0e4bbd6e",
    "Diversión":        "a1d0605a",
    "Servicios":        "0a9ef564",
    "Deuda":            "91ab4385",
    "Renta":            "eeb6e041",
    "MSI":              "1fc7eb0cbb92802b",
    "Automóvil":        "20f5ab24",
    "Ezra":             "3547eb0cbb92817b",
    "Restaurantes":     "3547eb0cbb9281e0",
    "Salud":            "3547eb0cbb9281a1ba5dfea0791b8d36",
    "Cuidado personal": "82916172",
}

# ─── REGLAS DE CATEGORÍA ─────────────────────────────────────────────────────
REGLAS_CONCEPTO = [
    (["walmart", "soriana", "costco", "bodega aurrera", "sam's"], "Super", "Despensa"),
    (["calii"], "Super", "Despensa"),
    (["zarapes"], "Restaurantes", "Despensa"),
    (["carnicería", "carniceria", "carnes especiales", "barranqueño", "barrangueno"], "Carnicería", "Despensa"),
    (["restaurante", "taqueria", "taquería", "tacos", "pizza", "sushi", "pollo bronco",
      "dq ", "dairy queen", "carl's", "carls", "mcdonalds", "burger", "kfc", "subway",
      "domino", "clip mx*rest", "payclip*rest", "la choco", "chocof"], "Restaurantes", "Restaurantes"),
    (["gasolina", "oxxo gas", "oxxogas", "bp ", "combustible"], "Gasolina", "Automóvil"),
    (["netflix", "spotify", "disney", "hbo", "apple tv", "paramount"], "Streaming", "Servicios"),
    (["izzi", "telmex", "adobe", "icloud", "capcut", "claude", "conekta*parco", "parco"], "Servicios", "Servicios"),
    (["google"], "Servicios", "Servicios"),
    (["cfe", "luz "], "Luz", "Servicios"),
    (["mapfre", "seguro auto", "qualitas"], "Seguro Auto", "Automóvil"),
    (["farmacia", "benavides", "guadalajara", "ahorro", "similares", "doctor", "hospital"], "Servicios", "Salud"),
    (["oxxo", "bae ", "naranjitas", "rancherita", "abarrotes", "minisuper", "seven"], "Abarrotes", "Despensa"),
    (["cine", "teatro", "concierto", "antro", "bar ", "cerveza"], "Salidas", "Diversión"),
    (["starbucks", "café", "cafe ", "helado", "nieve", "panadería"], "Treat", "Diversión"),
]

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

# ─── LÓGICA ──────────────────────────────────────────────────────────────────
def calcular_tarjeta(fecha, tarjeta_explicita=None):
    if tarjeta_explicita:
        return tarjeta_explicita.upper()
    return "BBVA05" if 5 <= fecha.day <= 11 else "BBVA12"

def calcular_mes(fecha, tarjeta):
    d, m, y = fecha.day, fecha.month, fecha.year
    if tarjeta == "BBVA05":
        mes_pago = m + 1 if d >= 5 else m
    elif tarjeta == "BBVA12":
        mes_pago = m + 2 if d >= 12 else m + 1
    elif tarjeta == "HEYB25":
        mes_pago = m + 2 if d >= 25 else m + 1
    elif tarjeta == "BMEX04":
        mes_pago = m + 1 if d >= 4 else m
    else:
        mes_pago = m + 1

    anio = y
    while mes_pago > 12:
        mes_pago -= 12
        anio += 1

    return f"{MESES_ESP[mes_pago]}{str(anio)[-2:]}"

def inferir_categoria(concepto):
    c = concepto.lower()
    for palabras, subcat, presu in REGLAS_CONCEPTO:
        for p in palabras:
            if p in c:
                return subcat, presu
    return "Abarrotes", "Despensa"

def parsear_fecha(tokens):
    hoy = datetime.date.today()
    for i, t in enumerate(tokens):
        tl = t.lower()
        if tl == "ayer":
            return hoy - datetime.timedelta(days=1), tokens[:i] + tokens[i+1:]
        if tl == "hoy":
            return hoy, tokens[:i] + tokens[i+1:]
        m = re.match(r'^(\d{1,2})[-/](\d{1,2})$', t)
        if m:
            try:
                return datetime.date(hoy.year, int(m.group(2)), int(m.group(1))), tokens[:i] + tokens[i+1:]
            except:
                pass
        m = re.match(r'^(\d{1,2})[-/]([a-z]+)$', tl)
        if m and m.group(2) in MESES_TEXTO:
            try:
                return datetime.date(hoy.year, MESES_TEXTO[m.group(2)], int(m.group(1))), tokens[:i] + tokens[i+1:]
            except:
                pass
    return hoy, tokens

def parsear_tarjeta(tokens):
    validas = ["BBVA05", "BBVA12", "HEYB25", "BMEX04", "EFVO"]
    for i, t in enumerate(tokens):
        if t.upper() in validas:
            return t.upper(), tokens[:i] + tokens[i+1:]
    return None, tokens

def parsear_monto(tokens):
    for i, t in enumerate(tokens):
        try:
            monto = float(t.replace("$", "").replace(",", ""))
            if monto > 0:
                return monto, tokens[:i] + tokens[i+1:]
        except:
            pass
    return None, tokens

def parsear_mensaje(texto):
    tokens = texto.strip().split()
    fecha, tokens = parsear_fecha(tokens)
    tarjeta_exp, tokens = parsear_tarjeta(tokens)
    monto, tokens = parsear_monto(tokens)
    concepto = " ".join(tokens).strip()

    if not concepto:
        raise ValueError("No encontré el concepto del gasto")
    if monto is None:
        raise ValueError("No encontré el monto")

    tarjeta = calcular_tarjeta(fecha, tarjeta_exp)
    mes = calcular_mes(fecha, tarjeta)
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

def guardar_en_notion(gasto):
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

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={"parent": {"database_id": NOTION_DATABASE_ID}, "properties": properties}
    )
    return r.status_code == 200, r.text

# ─── HANDLERS ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *¡Hola! Soy tu bot de gastos.*\n\n"
        "Escríbeme así:\n"
        "`Concepto Monto`\n\n"
        "Ejemplos:\n"
        "`Starbucks 150`\n"
        "`Gasolina 500 BBVA05`\n"
        "`Walmart 350 ayer`\n"
        "`Netflix 299 HEYB25`\n"
        "`Oxxo Gas 400 15-may`\n\n"
        "Tarjetas: BBVA05, BBVA12, HEYB25, BMEX04, EFVO",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    try:
        gasto = parsear_mensaje(texto)
        guardado, _ = guardar_en_notion(gasto)
        if guardado:
            await update.message.reply_text(
                f"✅ *Gasto guardado*\n\n"
                f"📌 *{gasto['concepto']}*\n"
                f"💰 ${gasto['monto']:,.2f}\n"
                f"📅 {gasto['fecha']}\n"
                f"💳 {gasto['tarjeta']}\n"
                f"🗓️ Mes: {gasto['mes']}\n"
                f"🏷️ {gasto['subcategoria']} → {gasto['presupuesto']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Error al guardar en Notion.")
    except ValueError as e:
        await update.message.reply_text(f"❓ {e}\n\nEjemplo: `Starbucks 150`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─── ARRANQUE ────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()
