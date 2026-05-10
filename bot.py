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

REGLAS_CONCEPTO = [
    (["walmart", "soriana", "costco", "bodega aurrera", "sam's"], "Super", "Despensa"),
    (["calii"], "Super", "Despensa"),
    (["zarapes"], "Restaurantes", "Despensa"),
    (["carniceria", "carnes especiales", "barrangueno"], "Carniceria", "Despensa"),
    (["restaurante", "taqueria", "tacos", "pizza", "sushi", "pollo bronco",
      "dq ", "dairy queen", "carl's", "mcdonalds", "burger", "kfc", "subway",
      "domino", "clip mx*rest", "payclip*rest", "la choco"], "Restaurantes", "Restaurantes"),
    (["gasolina", "oxxo gas", "oxxogas", "bp ", "combustible"], "Gasolina", "Automovil"),
    (["netflix", "spotify", "disney", "hbo", "apple tv", "paramount"], "Streaming", "Servicios"),
    (["izzi", "telmex", "adobe", "icloud", "capcut", "claude", "conekta*parco"], "Servicios", "Servicios"),
    (["google"], "Servicios", "Servicios"),
    (["cfe", "luz "], "Luz", "Servicios"),
    (["mapfre", "seguro auto", "qualitas"], "Seguro Auto", "Automovil"),
    (["farmacia", "benavides", "guadalajara", "ahorro", "similares", "doctor", "hospital"], "Servicios", "Salud"),
    (["oxxo", "bae ", "naranjitas", "rancherita", "abarrotes", "minisuper", "seven"], "Abarrotes", "Despensa"),
    (["cine", "teatro", "concierto", "antro", "bar ", "cerveza"], "Salidas", "Diversion"),
    (["starbucks", "cafe ", "helado", "nieve", "panaderia"], "Treat", "Diversion"),
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

def buscar_mes_id(mes_nombre):
    """Busca el ID de la pagina de mes en Notion"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    # Buscar en la base de datos de meses
    r = requests.post(
        "https://api.notion.com/v1/search",
        headers=headers,
        json={"query": mes_nombre, "filter": {"value": "page", "property": "object"}}
    )
    if r.status_code == 200:
        results = r.json().get("results", [])
        for page in results:
            title = page.get("properties", {}).get("Nombre", {}).get("title", [])
            if title and title[0].get("plain_text", "") == mes_nombre:
                return page["id"]
    return None

def guardar_en_notion(gasto):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    
    # Campos básicos que sabemos funcionan
    properties = {
        "Concepto": {"title": [{"text": {"content": gasto["concepto"]}}]},
        "Monto":    {"number": gasto["monto"]},
        "Fecha":    {"date": {"start": gasto["fecha"]}},
        "Estado de Cuenta": {"rich_text": [{"text": {"content": gasto["tarjeta"]}}]},
    }

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
        "Netflix 299 HEYB25\n\n"
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
