import os
import re
import datetime
import requests
import threading
import unicodedata
from difflib import SequenceMatcher
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, ConversationHandler

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN      = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN        = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID  = os.environ["NOTION_DATABASE_ID"]
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

USUARIOS_AUTORIZADOS = {8663298433, 8093171397}
USUARIOS_NOMBRES = {8663298433: "Jordi", 8093171397: "Nane"}
USUARIOS_NOTIFICAR = {8663298433: 8093171397, 8093171397: 8663298433}

MONTO_INUSUAL = 5000
CONFIRMAR_MONTO = 1
CONFIRMAR_CATEGORIA = 2

# ─── IDs NOTION VERIFICADOS ───────────────────────────────────────────────────
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

PRESUPUESTOS_IDS = {
    "Despensa":         "0e4bbd6e13b34972b39f14f76eb61d7d",
    "Diversión":        "a1d0605a28694b0baefdc43ac75a798a",
    "Servicios":        "0a9ef564f8944cc088e302e64ad702b6",
    "Automovil":        "20f5ab24f9ca4185af6a34254ab3a630",
    "Restaurantes":     "3547eb0cbb9281e08ef5f3666e091a44",
    "Salud":            "3547eb0cbb9281a1ba5dfea0791b8d36",
    "Deuda":            "91ab43856d1e4ae69f21f4203eeb3c54",
    "MSI":              "1fc7eb0cbb92802ba323cfc943dc0f2c",
    "Renta":            "eeb6e04137c248468f641a5044b16545",
    "Ezra":             "3547eb0cbb92817baaa9f6681e6bbabc",
    "Cuidado personal": "829161723b0b49bf8787663a89c7248d",
    "Otros":            "1ea7eb0cbb9280cbbe43c1bd54396691",
    "Entretenimiento":  "3547eb0cbb92815d8248db75a759646b",
}

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

# ─── REGLAS DE CATEGORÍA (enriquecidas con comportamiento real) ───────────────
REGLAS_CONCEPTO = [
    # SUPERMERCADOS GRANDES → Super/Despensa
    (["walmart", "soriana", "costco", "bodega aurrera", "bae plaza", "bae ",
      "chedraui", "la comer", "sam's", "superama"], "Super", "Despensa"),

    # CALII CALII → Super/Despensa (excepción especial)
    (["calii"], "Super", "Despensa"),

    # ZARAPES → Restaurantes/Despensa (excepción especial)
    (["zarapes", "merpago*zarapes"], "Restaurantes", "Despensa"),

    # CARNICERÍA / PESCADERÍA → Carniceria/Despensa
    (["carniceria", "carnes especiales", "barrangueno", "el barranqueno",
      "pescaderia", "pescaderia", "abts", "altamez", "mariscos"], "Carniceria", "Despensa"),

    # RESTAURANTES → Restaurantes/Restaurantes
    (["restaurante", "taqueria", "tacos", "pizza", "sushi", "pollo bronco",
      "dq ", "dairy queen", "carl's", "mcdonald", "burger", "kfc", "subway",
      "domino", "clip mx*rest", "payclip*rest", "la choco", "mamma farina",
      "dolce natura", "los elotis", "punto sur", "barbacos", "barbacoa",
      "velma", "calena", "bistro", "bistro", "brüm", "brum", "meridiao",
      "boucherie", "uber eats", "rappi", "la taquiza", "el fogon",
      "applebees", "chilis", "vips", "ihop", "el torito"], "Restaurantes", "Restaurantes"),

    # GASOLINA → Gasolina/Automovil
    # CRÍTICO: Oxxo Gas ≠ Oxxo tienda
    (["oxxo gas", "oxxogas", "oxxo gaspaseos", "gasolina", "bp ", "shell ",
      "petro", "combustible", "hidrosina"], "Gasolina", "Automovil"),

    # STREAMING → Streaming/Servicios
    (["netflix", "spotify", "disney", "hbo", "apple tv", "paramount",
      "crunchyroll", "max ", "prime video", "apple one"], "Streaming", "Servicios"),

    # SERVICIOS DIGITALES → Servicios/Servicios
    (["izzi", "telmex", "adobe", "icloud", "capcut", "claude", "conekta*parco",
      "creative market", "dropbox", "notion", "figma", "canva",
      "microsoft", "office 365", "chatgpt", "openai"], "Servicios", "Servicios"),
    (["google"], "Servicios", "Servicios"),

    # AT&T → Servicios/Servicios
    (["at&t", "att "], "Servicios", "Servicios"),

    # LUZ → Luz/Servicios
    (["cfe"], "Luz", "Servicios"),

    # SEGURO AUTO → Seguro Auto/Automovil
    (["mapfre", "seguro auto", "qualitas", "gnp auto", "axa "], "Seguro Auto", "Automovil"),

    # MANTENIMIENTO AUTO → Servicios/Automovil
    (["autolavado", "refaccion", "mecanico", "llantas", "pennzoil",
      "valvoline", "jiffy lube"], "Servicios", "Automovil"),

    # SALUD → Servicios/Salud
    (["farmacia guadalajara", "farmacia benavides", "farmacias del ahorro",
      "farmacia similares", "farmacia san pablo", "doctor", "hospital",
      "clinica", "medico", "consulta", "gerber", "nutrileche",
      "pedialyte", "medicamento", "farmacia"], "Servicios", "Salud"),

    # ABARROTES LOCALES → Abarrotes/Despensa
    # CRÍTICO: Oxxo tienda ≠ Oxxo Gas
    (["oxxo", "naranjitas", "rancherita", "super rancherita", "abarrotes",
      "minisuper", "seven", "mercado ", "tianguis", "barreto",
      "merpago*abarrotes", "merpago*gro", "abts pegaso",
      "la rancherita", "abarrotes barreto"], "Abarrotes", "Despensa"),

    # SALIDAS → Salidas/Diversión
    (["parco", "conekta*parco", "estacionamiento", "cinepolis", "cinemex",
      "cine ", "teatro", "concierto", "evento", "antro", "bar ",
      "boliche", "entretenimiento"], "Salidas", "Diversión"),

    # TREAT → Treat/Diversión
    (["starbucks", "cafe ", "coffee", "brüm", "brum",
      "helado", "nieve", "nieves", "paleta", "panaderia",
      "panaderia", "pasteleria", "reposteria", "chocolates",
      "gustito", "heladeria", "creperia"], "Treat", "Diversión"),

    # AMAZON → Otros/Otros
    (["amazon"], "Otros", "Otros"),

    # UBER (transporte, no Uber Eats) → Servicios/Automovil
    (["uber ", "didi ", "cabify"], "Servicios", "Automovil"),
]

# ─── UTILIDADES ───────────────────────────────────────────────────────────────
def normalizar(texto):
    texto = texto.lower().strip()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto

def similitud(a, b):
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

def buscar_en_google_maps(concepto):
    if not GOOGLE_MAPS_API_KEY:
        return None
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "places.types,places.displayName"
        }
        payload = {
            "textQuery": f"{concepto} Guadalajara Mexico",
            "locationBias": {
                "circle": {
                    "center": {"latitude": 20.6597, "longitude": -103.3496},
                    "radius": 50000.0
                }
            }
        }
        r = requests.post(url, headers=headers, json=payload, timeout=3)
        if r.status_code == 200:
            places = r.json().get("places", [])
            if places:
                return places[0].get("types", [])
    except:
        pass
    return None

MAPS_TIPO_CATEGORIA = {
    "restaurant": ("Restaurantes", "Restaurantes"),
    "cafe": ("Treat", "Diversión"),
    "bakery": ("Treat", "Diversión"),
    "supermarket": ("Super", "Despensa"),
    "grocery_or_supermarket": ("Super", "Despensa"),
    "convenience_store": ("Abarrotes", "Despensa"),
    "gas_station": ("Gasolina", "Automovil"),
    "pharmacy": ("Servicios", "Salud"),
    "hospital": ("Servicios", "Salud"),
    "car_wash": ("Servicios", "Automovil"),
    "car_repair": ("Servicios", "Automovil"),
    "movie_theater": ("Salidas", "Diversión"),
    "night_club": ("Salidas", "Diversión"),
    "bar": ("Salidas", "Diversión"),
}

def categoria_desde_maps(tipos):
    if not tipos:
        return None, None
    for tipo in tipos:
        for key, val in MAPS_TIPO_CATEGORIA.items():
            if key in tipo:
                return val
    return None, None

def inferir_categoria(concepto):
    c = normalizar(concepto)

    # 1. Coincidencia exacta en reglas
    for palabras, subcat, presu in REGLAS_CONCEPTO:
        for p in palabras:
            if normalizar(p) in c:
                return subcat, presu, True

    # 2. Similitud por typos (min 4 chars, min 80% similitud)
    mejor_score = 0
    mejor_resultado = None
    for palabras, subcat, presu in REGLAS_CONCEPTO:
        for p in palabras:
            if len(p) < 4:
                continue
            score = similitud(concepto, p)
            if score > mejor_score and score > 0.80:
                mejor_score = score
                mejor_resultado = (subcat, presu)
    if mejor_resultado:
        return mejor_resultado[0], mejor_resultado[1], True

    # 3. Google Maps
    tipos_maps = buscar_en_google_maps(concepto)
    subcat_maps, presu_maps = categoria_desde_maps(tipos_maps)
    if subcat_maps:
        return subcat_maps, presu_maps, True

    # 4. No encontrado — pedir confirmación
    return "Abarrotes", "Despensa", False

# ─── LÓGICA DE FECHAS Y TARJETAS ─────────────────────────────────────────────
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

def parsear_fecha(tokens):
    tz = __import__('zoneinfo').ZoneInfo("America/Mexico_City")
    hoy = datetime.datetime.now(tz).date()
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
        raise ValueError("No encontré el concepto del gasto")
    if monto is None:
        raise ValueError("No encontré el monto")
    tarjeta = calcular_tarjeta(fecha, tarjeta_exp)
    mes = calcular_mes(fecha, tarjeta)
    subcategoria, presupuesto, seguro = inferir_categoria(concepto)
    return {
        "concepto": concepto.title(),
        "monto": monto,
        "fecha": fecha.strftime("%Y-%m-%d"),
        "tarjeta": tarjeta,
        "mes": mes,
        "subcategoria": subcategoria,
        "presupuesto": presupuesto,
        "seguro": seguro,
    }

# ─── NOTION ───────────────────────────────────────────────────────────────────
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

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def formato_mensaje(gasto, prefijo="✅ Gasto guardado", nombre=None):
    from datetime import datetime as dt
    fecha_fmt = dt.strptime(gasto['fecha'], '%Y-%m-%d').strftime('%d %b %Y').lower()
    encabezado = f"🔔 Nuevo gasto de {nombre}" if nombre else prefijo
    return (
        f"{encabezado}\n\n"
        f"📌 {gasto['concepto']}\n"
        f"💵 ${gasto['monto']:,.2f}\n"
        f"🗓️ {fecha_fmt}\n"
        f"💳 {gasto['tarjeta']}  •  Mes: {gasto['mes']}\n"
        f"🏷️ {gasto['subcategoria']}  •  {gasto['presupuesto']}"
    )

async def enviar_y_notificar(update, context, gasto):
    user_id = update.effective_user.id
    nombre = USUARIOS_NOMBRES.get(user_id, "Alguien")
    await update.message.reply_text(formato_mensaje(gasto))
    notificar_a = USUARIOS_NOTIFICAR.get(user_id)
    if notificar_a:
        await context.bot.send_message(
            chat_id=notificar_a,
            text=formato_mensaje(gasto, nombre=nombre)
        )

# ─── HANDLERS ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        await update.message.reply_text("⛔ No tienes acceso.")
        return
    await update.message.reply_text(
        "👋 Hola! Soy tu bot de gastos.\n\n"
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
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        await update.message.reply_text("⛔ No tienes acceso.")
        return ConversationHandler.END

    texto = update.message.text.strip()
    try:
        gasto = parsear_mensaje(texto)

        # MEJORA 4: Detectar monto inusual
        if gasto["monto"] >= MONTO_INUSUAL:
            context.user_data["gasto_pendiente"] = gasto
            await update.message.reply_text(
                f"⚠️ El monto ${gasto['monto']:,.2f} es inusual.\n"
                f"¿Confirmas el gasto de {gasto['concepto']}?\n\n"
                f"Responde SI para guardar o NO para cancelar.",
                reply_markup=ReplyKeyboardMarkup([["SI", "NO"]], one_time_keyboard=True, resize_keyboard=True)
            )
            return CONFIRMAR_MONTO

        # MEJORA 3: Preguntar categoría si no está seguro
        if not gasto["seguro"]:
            context.user_data["gasto_pendiente"] = gasto
            opciones = [
                ["Restaurantes", "Super"],
                ["Abarrotes", "Gasolina"],
                ["Servicios", "Treat"],
                ["Salidas", "Otros"]
            ]
            await update.message.reply_text(
                f"❓ No reconocí bien '{gasto['concepto']}'.\n"
                f"¿En qué categoría va?",
                reply_markup=ReplyKeyboardMarkup(opciones, one_time_keyboard=True, resize_keyboard=True)
            )
            return CONFIRMAR_CATEGORIA

        guardado, _ = guardar_en_notion(gasto)
        if guardado:
            await enviar_y_notificar(update, context, gasto)
        else:
            await update.message.reply_text("⚠️ Error al guardar en Notion.")

    except ValueError as e:
        await update.message.reply_text(f"❓ {e}\n\nEjemplo: Starbucks 150")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    return ConversationHandler.END

async def confirmar_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    respuesta = update.message.text.strip().upper()
    gasto = context.user_data.get("gasto_pendiente")
    if respuesta == "SI" and gasto:
        guardado, _ = guardar_en_notion(gasto)
        if guardado:
            await enviar_y_notificar(update, context, gasto)
        else:
            await update.message.reply_text("⚠️ Error al guardar en Notion.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ Gasto cancelado.", reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("gasto_pendiente", None)
    return ConversationHandler.END

async def confirmar_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categoria = update.message.text.strip()
    gasto = context.user_data.get("gasto_pendiente")
    if not gasto:
        await update.message.reply_text("❌ Error, intenta de nuevo.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Mapear categoría seleccionada a presupuesto
    CATEGORIA_PRESUPUESTO = {
        "Restaurantes": "Restaurantes",
        "Super": "Despensa",
        "Abarrotes": "Despensa",
        "Gasolina": "Automovil",
        "Servicios": "Servicios",
        "Treat": "Diversión",
        "Salidas": "Diversión",
        "Otros": "Otros",
    }
    gasto["subcategoria"] = categoria
    gasto["presupuesto"] = CATEGORIA_PRESUPUESTO.get(categoria, "Otros")

    guardado, _ = guardar_en_notion(gasto)
    if guardado:
        await update.message.reply_text(
            formato_mensaje(gasto),
            reply_markup=ReplyKeyboardRemove()
        )
        notificar_a = USUARIOS_NOTIFICAR.get(update.effective_user.id)
        nombre = USUARIOS_NOMBRES.get(update.effective_user.id, "Alguien")
        if notificar_a:
            await context.bot.send_message(
                chat_id=notificar_a,
                text=formato_mensaje(gasto, nombre=nombre)
            )
    else:
        await update.message.reply_text("⚠️ Error al guardar en Notion.", reply_markup=ReplyKeyboardRemove())

    context.user_data.pop("gasto_pendiente", None)
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("gasto_pendiente", None)
    await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ─── SERVIDOR HTTP ────────────────────────────────────────────────────────────
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

# ─── ARRANQUE ────────────────────────────────────────────────────────────────
async def main():
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Limpiar instancias previas para evitar conflictos
    await app.bot.delete_webhook(drop_pending_updates=True)

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            CONFIRMAR_MONTO:     [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_monto)],
            CONFIRMAR_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_categoria)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    print("🤖 Bot corriendo con todas las mejoras...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
