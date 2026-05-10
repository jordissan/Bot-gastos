import os
import re
import datetime
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN       = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# IDs verificados de Subcategorias
SUBCATEGORIAS_IDS = {
    "Super":           "bf7d4b7d0445441ab89b53eec946d028",
    "Abarrotes":       "3587eb0cbb9280c58919c55b065c1e19",
    "Carniceria":      "6a734da3d457465db419f195de13909b",
    "Restaurantes":    "1cf748f0639e41469ae2cc73aa86e10a",
    "Gasolina":        "8382b85617f342afa50ed56ca48ed9d3",
    "Servicios":       "b4d2856cb9a44fd584904aabcc007008",
    "Streaming":       "1d87eb0cbb9280a186f9f369501da604",
    "Treat":           "1d87eb0cbb9280d5b5b0e9efd29e46bf",
    "Salidas":         "1d87eb0cbb9280c1b4b7d3beeb2b1ebc",
    "Luz":             "bf545e8169f840eda0ca126164e105b8",
    "Seguro Auto":     "cf81abcd84824b82b71455913fefdd2a",
    "MSI":             "1fa7eb0cbb928050a619e2105a4b77e4",
    "Deudas":          "583b7dd3eb694921ac327e66821dd715",
    "Otros":           "fd99fde0fa724f41a0ffeb7ee9425ec8",
}

# IDs verificados de Presupuestos
PRESUPUESTOS_IDS = {
    "Despensa":        "0e4bbd6e13b34972b39f14f76eb61d7d",
    "Diversión":       "a1d0605a28694b0baefdc43ac75a798a",
    "Servicios":       "0a9ef564f8944cc088e302e64ad702b6",
    "Automovil":       "20f5ab24f9ca4185af6a34254ab3a630",
    "Restaurantes":    "3547eb0cbb9281e08ef5f3666e091a44",
    "Salud":           "3547eb0cbb9281a1ba5dfea0791b8d36",
    "Deuda":           "91ab43856d1e4ae69f21f4203eeb3c54",
    "MSI":             "1fc7eb0cbb92802ba323cfc943dc0f2c",
    "Renta":           "eeb6e04137c248468f641a5044b16545",
    "Ezra":            "3547eb0cbb92817baaa9f6681e6bbabc",
    "Cuidado personal":"829161723b0b49bf8787663a89c7248d",
    "Otros":           "1ea7eb0cbb9280cbbe43c1bd54396691",
}

# IDs verificados de Meses 2026
MESES_IDS = {
    "ENE26": "3487eb0cbb92800a9e6fcf9a2d712e40",
    "FEB26": "3487eb0cbb928062b309eecc92f4035e",
    "MAR26": "3487eb0cbb9280648018ffe4171ad173",
    "ABR26": "3447eb0cbb928007822cdf54ad63c9de",
    "MAY26": "3447eb0cbb928051bddee3da069f31f7",
    "JUN26": "3447eb0cbb9280678db1fd1faa5a98cd",
    "JUL26": "3447eb0cbb9280b3ac4bf0106118f576",
    "AGO26": "3447eb0cbb92808daae4d029edda14b7",
    "SEP26": "3447eb0cbb9280ae861bc6db426e8c58",
    "OCT26": "3447eb0cbb928093bf97e20b4540ad79",
    "NOV26": "3447eb0cbb928007b6f5c3fbab7eecd6",
    "DIC26": "3447eb0cbb928049a264d12ff9048685",
}

REGLAS_CONCEPTO = [
    (["walmart", "soriana", "costco", "bodega aurrera", "sam's"], "Super", "Despensa"),
    (["calii"], "Super", "Despensa"),
    (["zarapes"], "Restaurantes", "Despensa"),
    (["carniceria", "carnes especiales", "barrangueno"], "Carniceria", "Despensa"),
    (["restaurante", "taqueria", "tacos", "pizza", "sushi", "pollo bronco",
      "dq ", "dairy queen", "carl's", "mcdonalds", "burger", "kfc", "subway",
      "domino", "clip mx*rest", "payclip*rest", "la choco"], "Restaurantes", "Restaurantes"),
    (["gasolina", "oxxo gas", "oxxogas", "combustible"], "Gasolina", "Automovil"),
    (["netflix", "spotify", "disney", "hbo", "apple tv", "paramount"], "Streaming", "Servicios"),
    (["izzi", "telmex", "adobe", "icloud", "capcut", "claude", "conekta*parco"], "Servicios", "Servicios"),
    (["google"], "Servicios", "Servicios"),
    (["cfe"], "Luz", "Servicios"),
    (["mapfre", "seguro auto", "qualitas"], "Seguro Auto", "Automovil"),
    (["farmacia", "benavides", "guadalajara", "ahorro", "similares", "doctor", "hospital"], "Servicios", "Salud"),
    (["oxxo", "bae ", "naranjitas", "rancherita", "abarrotes", "minisuper", "seven"], "Abarrotes", "Despensa"),
    (["cine", "teatro", "concierto", "antro", "bar "], "Salidas", "Diversión"),
    (["starbucks", "cafe ", "helado", "nieve", "panaderia"], "Treat", "Diversión"),
]

MESES_ESP = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",
             7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}
MESES_TEXTO = {
    "ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,
    "jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}

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
            except: pass
        m = re.match(r'^(\d{1,2})[-/]([a-z]+)$', tl)
        if m and m.group(2) in MESES_TEXTO:
            try:
                return datetime.date(hoy.year, MESES_TEXTO[m.group(2)], int(m.group(1))), tokens[:i] + tokens[i+1:]
            except: pass
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
        except: pass
    return None, tokens

def parsear_mensaje(texto):
    tokens = texto.strip().split()
    fecha, tokens = parsear_fecha(tokens)
    tarjeta_exp, tokens = parsear_tarjeta(tokens)
    monto, tokens = parsear_monto(tokens)
    concepto = " ".join(tokens).strip()
    if not concepto:
        raise ValueError("No encontre el concepto del gasto")
    if monto is None:
        raise ValueError("No encontre el monto")
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

    properties = {
        "Concepto": {"title": [{"text": {"content": gasto["concepto"]}}]},
        "Monto":    {"number": gasto["monto"]},
        "Fecha":    {"date": {"start": gasto["fecha"]}},
        "Estado de Cuenta": {"rich_text": [{"text": {"content": gasto["tarjeta"]}}]},
        "Pago":     {"select": {"name": gasto["tarjeta"]}},
    }

    mes_id = MESES_IDS.get(gasto["mes"])
    if mes_id:
        properties["Mes"] = {"relation": [{"id": mes_id}]}

    subcat_id = SUBCATEGORIAS_IDS.get(gasto["subcategoria"])
    if subcat_id:
        properties["Subcategoria"] = {"relation": [{"id": subcat_id}]}

    presu_id = PRESUPUESTOS_IDS.get(gasto["presupuesto"])
    if presu_id:
        properties["Presupuesto"] = {"relation": [{"id": presu_id}]}

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={"parent": {"database_id": NOTION_DATABASE_ID}, "properties": properties}
    )
    return r.status_code == 200, r.text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola! Soy tu bot de gastos.\n\n"
        "Escríbeme así: Concepto Monto\n\n"
        "Ejemplos:\n"
        "Starbucks 150\n"
        "Gasolina 500 BBVA05\n"
        "Walmart 350 ayer\n"
        "Netflix 299 HEYB25\n"
        "Oxxo Gas 400 15-may\n\n"
        "Tarjetas: BBVA05, BBVA12, HEYB25, BMEX04, EFVO"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    try:
        gasto = parsear_mensaje(texto)
        guardado, respuesta = guardar_en_notion(gasto)
        if guardado:
            await update.message.reply_text(
                f"Gasto guardado\n\n"
                f"{gasto['concepto']}\n"
                f"${gasto['monto']:,.2f}\n"
                f"{gasto['fecha']}\n"
                f"{gasto['tarjeta']}\n"
                f"Mes: {gasto['mes']}\n"
                f"{gasto['subcategoria']} -> {gasto['presupuesto']}"
            )
        else:
            await update.message.reply_text(f"Error Notion: {respuesta[:300]}")
    except ValueError as e:
        await update.message.reply_text(f"Error: {e}\n\nEjemplo: Starbucks 150")
    except Exception as e:
        await update.message.reply_text(f"Error inesperado: {e}")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def main():
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()
