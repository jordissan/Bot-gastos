import os
import re
import datetime
import requests
import threading
import unicodedata
from difflib import SequenceMatcher
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# CONFIGURACION
TELEGRAM_TOKEN      = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN        = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID  = os.environ["NOTION_DATABASE_ID"]
NOTION_APRENDIZAJE_ID = "3ba6f37c717948a1a6aeac3b384ff33c"
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

USUARIOS_AUTORIZADOS = {8663298433, 8093171397}
USUARIOS_NOMBRES = {8663298433: "Jordi", 8093171397: "Nane"}
USUARIOS_NOTIFICAR = {8663298433: 8093171397, 8093171397: 8663298433}

MONTO_INUSUAL = 5000
CONFIRMAR_MONTO = 1
CONFIRMAR_CATEGORIA = 2
CORREGIR_ELEGIR = 3
CORREGIR_CATEGORIA = 4
CORREGIR_PRESUPUESTO = 5

# IDs NOTION
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

REGLAS_CONCEPTO = [
    (["walmart", "soriana", "costco", "bodega aurrera", "bae plaza", "bae ",
      "chedraui", "la comer", "sam's", "superama"], "Super", "Despensa"),
    (["calii"], "Super", "Despensa"),
    (["zarapes", "merpago*zarapes"], "Restaurantes", "Despensa"),
    (["carniceria", "carnes especiales", "barrangueno", "el barranqueno",
      "pescaderia", "abts", "altamez", "mariscos"], "Carniceria", "Despensa"),
    (["restaurante", "taqueria", "tacos", "pizza", "sushi", "pollo bronco",
      "dq ", "dairy queen", "carl's", "mcdonald", "burger", "kfc", "subway",
      "domino", "clip mx*rest", "payclip*rest", "la choco", "mamma farina",
      "dolce natura", "los elotis", "punto sur", "barbacos", "barbacoa",
      "velma", "calena", "bistro", "brüm", "brum", "meridiao",
      "boucherie", "uber eats", "rappi", "la taquiza", "el fogon",
      "applebees", "chilis", "vips", "ihop", "el torito"], "Restaurantes", "Restaurantes"),
    (["oxxo gas", "oxxogas", "oxxo gaspaseos", "gasolina", "bp ", "shell ",
      "petro", "combustible", "hidrosina"], "Gasolina", "Automovil"),
    (["netflix", "spotify", "disney", "hbo", "apple tv", "paramount",
      "crunchyroll", "max ", "prime video", "apple one"], "Streaming", "Servicios"),
    (["izzi", "telmex", "adobe", "icloud", "capcut", "claude", "conekta*parco",
      "creative market", "dropbox", "figma", "canva", "microsoft", "chatgpt"], "Servicios", "Servicios"),
    (["google"], "Servicios", "Servicios"),
    (["at&t", "att "], "Servicios", "Servicios"),
    (["cfe"], "Luz", "Servicios"),
    (["mapfre", "seguro auto", "qualitas", "gnp auto", "axa "], "Seguro Auto", "Automovil"),
    (["autolavado", "refaccion", "mecanico", "llantas", "pennzoil"], "Servicios", "Automovil"),
    (["farmacia guadalajara", "farmacia benavides", "farmacias del ahorro",
      "farmacia similares", "doctor", "hospital", "clinica", "medico",
      "consulta", "gerber", "nutrileche", "pedialyte", "farmacia"], "Servicios", "Salud"),
    (["oxxo", "naranjitas", "rancherita", "super rancherita", "abarrotes",
      "minisuper", "seven", "mercado ", "tianguis", "barreto",
      "merpago*abarrotes", "merpago*gro"], "Abarrotes", "Despensa"),
    (["parco", "conekta*parco", "estacionamiento", "cinepolis", "cinemex",
      "cine ", "teatro", "concierto", "evento", "antro", "bar "], "Salidas", "Diversión"),
    (["starbucks", "cafe ", "coffee", "brüm", "brum",
      "helado", "nieve", "nieves", "paleta", "panaderia",
      "pasteleria", "reposteria", "chocolates"], "Treat", "Diversión"),
    (["amazon"], "Otros", "Otros"),
    (["uber ", "didi ", "cabify"], "Servicios", "Automovil"),
]

MESES_ESP = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",
             7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}
MESES_TEXTO = {
    "ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,
    "jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}

# HISTORIAL DE GASTOS RECIENTES (en memoria)
historial_gastos = []  # Lista de dicts con {concepto, monto, fecha, tarjeta, mes, subcategoria, presupuesto, notion_id}

# UTILIDADES
def normalizar(texto):
    texto = texto.lower().strip()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto

def similitud(a, b):
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()

def buscar_en_aprendizaje(concepto):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    r = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",
        headers=headers,
        json={"filter": {"property": "Concepto", "title": {"equals": concepto.lower()}}}
    )
    if r.status_code == 200:
        results = r.json().get("results", [])
        if results:
            props = results[0]["properties"]
            subcat = props.get("Subcategoria", {}).get("rich_text", [])
            presu = props.get("Presupuesto", {}).get("rich_text", [])
            if subcat and presu:
                return subcat[0]["text"]["content"], presu[0]["text"]["content"]
    return None, None

def guardar_en_aprendizaje(concepto, subcategoria, presupuesto):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    # Verificar si ya existe
    r = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",
        headers=headers,
        json={"filter": {"property": "Concepto", "title": {"equals": concepto.lower()}}}
    )
    if r.status_code == 200:
        results = r.json().get("results", [])
        if results:
            # Actualizar
            page_id = results[0]["id"]
            usos_actual = results[0]["properties"].get("Usos", {}).get("number", 0) or 0
            requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"properties": {
                    "Subcategoria": {"rich_text": [{"text": {"content": subcategoria}}]},
                    "Presupuesto": {"rich_text": [{"text": {"content": presupuesto}}]},
                    "Usos": {"number": usos_actual + 1}
                }}
            )
            return
    # Crear nuevo
    requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json={
            "parent": {"database_id": NOTION_APRENDIZAJE_ID},
            "properties": {
                "Concepto": {"title": [{"text": {"content": concepto.lower()}}]},
                "Subcategoria": {"rich_text": [{"text": {"content": subcategoria}}]},
                "Presupuesto": {"rich_text": [{"text": {"content": presupuesto}}]},
                "Usos": {"number": 1}
            }
        }
    )

def buscar_en_google_maps(concepto):
    if not GOOGLE_MAPS_API_KEY:
        return None
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "places.types"
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
    # 1. Reglas hardcodeadas
    for palabras, subcat, presu in REGLAS_CONCEPTO:
        for p in palabras:
            if normalizar(p) in c:
                return subcat, presu, True
    # 2. Aprendizaje en Notion
    subcat_ap, presu_ap = buscar_en_aprendizaje(concepto)
    if subcat_ap and presu_ap:
        return subcat_ap, presu_ap, True
    # 3. Similitud typos
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
    # 4. Google Maps
    tipos_maps = buscar_en_google_maps(concepto)
    subcat_maps, presu_maps = categoria_desde_maps(tipos_maps)
    if subcat_maps:
        return subcat_maps, presu_maps, True
    # 5. No encontrado
    return "Abarrotes", "Despensa", False

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
    import zoneinfo
    tz = zoneinfo.ZoneInfo("America/Mexico_City")
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
        raise ValueError("No encontre el concepto del gasto")
    if monto is None:
        raise ValueError("No encontre el monto")
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
    return r.status_code == 200, r.json().get("id", ""), r.text

def actualizar_en_notion(page_id, subcategoria, presupuesto):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    properties = {}
    subcat_id = SUBCATEGORIAS_IDS.get(subcategoria)
    if subcat_id:
        properties["Subcategoria"] = {"relation": [{"id": subcat_id}]}
    presu_id = PRESUPUESTOS_IDS.get(presupuesto)
    if presu_id:
        properties["Presupuesto"] = {"relation": [{"id": presu_id}]}
    r = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=headers,
        json={"properties": properties}
    )
    return r.status_code == 200

def formato_mensaje(gasto, prefijo="Gasto guardado", nombre=None):
    from datetime import datetime as dt
    fecha_fmt = dt.strptime(gasto['fecha'], '%Y-%m-%d').strftime('%d %b %Y').lower()
    encabezado = f"Nuevo gasto de {nombre}" if nombre else prefijo
    emoji = "checkmark" if not nombre else "bell"
    return (
        f"{'Nuevo gasto de ' + nombre if nombre else chr(9989) + ' Gasto guardado'}\n\n"
        f"📌 {gasto['concepto']}\n"
        f"💵 ${gasto['monto']:,.2f}\n"
        f"🗓️ {fecha_fmt}\n"
        f"💳 {gasto['tarjeta']}  •  Mes: {gasto['mes']}\n"
        f"🏷️ {gasto['subcategoria']}  •  {gasto['presupuesto']}"
    )

async def enviar_y_notificar(update, context, gasto, notion_id):
    global historial_gastos
    user_id = update.effective_user.id
    nombre = USUARIOS_NOMBRES.get(user_id, "Alguien")

    # Guardar en historial
    gasto_con_id = {**gasto, "notion_id": notion_id}
    historial_gastos.insert(0, gasto_con_id)
    historial_gastos = historial_gastos[:10]  # Guardar solo los 10 últimos

    await update.message.reply_text(formato_mensaje(gasto), reply_markup=ReplyKeyboardRemove())

    # Notificar con botón de corregir
    notificar_a = USUARIOS_NOTIFICAR.get(user_id)
    if notificar_a:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Corregir categoría", callback_data=f"corregir:{notion_id}:{gasto['concepto']}")
        ]])
        await context.bot.send_message(
            chat_id=notificar_a,
            text=f"🔔 Nuevo gasto de {nombre}\n\n"
                 f"📌 {gasto['concepto']}\n"
                 f"💵 ${gasto['monto']:,.2f}\n"
                 f"🗓️ {gasto['fecha']}\n"
                 f"💳 {gasto['tarjeta']}  •  Mes: {gasto['mes']}\n"
                 f"🏷️ {gasto['subcategoria']}  •  {gasto['presupuesto']}",
            reply_markup=keyboard
        )

# COMANDO /corregir
async def cmd_corregir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END

    if not historial_gastos:
        await update.message.reply_text("No hay gastos recientes para corregir.")
        return ConversationHandler.END

    ultimos = historial_gastos[:3]
    texto = "Elige el gasto a corregir:\n\n"
    opciones = []
    for i, g in enumerate(ultimos):
        texto += f"{i+1}. {g['concepto']} ${g['monto']:,.2f} ({g['subcategoria']})\n"
        opciones.append([f"{i+1}. {g['concepto']} ${g['monto']:,.2f}"])

    await update.message.reply_text(
        texto,
        reply_markup=ReplyKeyboardMarkup(opciones, one_time_keyboard=True, resize_keyboard=True)
    )
    return CORREGIR_ELEGIR

async def corregir_elegir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    try:
        idx = int(texto[0]) - 1
        gasto = historial_gastos[idx]
        context.user_data["gasto_corregir"] = gasto
    except:
        await update.message.reply_text("Opcion no valida.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    opciones = [
        ["Restaurantes", "Super"],
        ["Abarrotes", "Gasolina"],
        ["Servicios", "Treat"],
        ["Salidas", "Streaming"],
        ["Luz", "Seguro Auto"],
        ["Otros", "Carniceria"],
    ]
    await update.message.reply_text(
        f"Corriendo: {gasto['concepto']}\n\nElige la nueva subcategoria:",
        reply_markup=ReplyKeyboardMarkup(opciones, one_time_keyboard=True, resize_keyboard=True)
    )
    return CORREGIR_CATEGORIA

async def corregir_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nueva_sub = update.message.text.strip()
    context.user_data["nueva_subcategoria"] = nueva_sub

    CATEGORIA_PRESUPUESTO = {
        "Restaurantes": ["Restaurantes", "Despensa"],
        "Super": ["Despensa"],
        "Abarrotes": ["Despensa"],
        "Gasolina": ["Automovil"],
        "Servicios": ["Servicios", "Automovil", "Salud"],
        "Treat": ["Diversión"],
        "Salidas": ["Diversión"],
        "Streaming": ["Servicios"],
        "Luz": ["Servicios"],
        "Seguro Auto": ["Automovil"],
        "Otros": ["Otros"],
        "Carniceria": ["Despensa"],
    }
    presupuestos = CATEGORIA_PRESUPUESTO.get(nueva_sub, ["Otros"])
    if len(presupuestos) == 1:
        context.user_data["nuevo_presupuesto"] = presupuestos[0]
        return await aplicar_correccion(update, context)

    await update.message.reply_text(
        f"Elige el presupuesto:",
        reply_markup=ReplyKeyboardMarkup([[p] for p in presupuestos], one_time_keyboard=True, resize_keyboard=True)
    )
    return CORREGIR_PRESUPUESTO

async def corregir_presupuesto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nuevo_presupuesto"] = update.message.text.strip()
    return await aplicar_correccion(update, context)

async def aplicar_correccion(update, context):
    gasto = context.user_data.get("gasto_corregir")
    nueva_sub = context.user_data.get("nueva_subcategoria")
    nuevo_presu = context.user_data.get("nuevo_presupuesto")

    if not gasto or not nueva_sub or not nuevo_presu:
        await update.message.reply_text("Error al corregir.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    exito = actualizar_en_notion(gasto["notion_id"], nueva_sub, nuevo_presu)

    if exito:
        # Actualizar historial en memoria
        for g in historial_gastos:
            if g["notion_id"] == gasto["notion_id"]:
                g["subcategoria"] = nueva_sub
                g["presupuesto"] = nuevo_presu

        # Guardar aprendizaje
        guardar_en_aprendizaje(gasto["concepto"].lower(), nueva_sub, nuevo_presu)

        await update.message.reply_text(
            f"Corregido en Notion y aprendizaje guardado\n\n"
            f"📌 {gasto['concepto']}\n"
            f"🏷️ {nueva_sub}  •  {nuevo_presu}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text("Error al actualizar Notion.", reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return ConversationHandler.END

# CALLBACK BOTON INLINE (desde notificacion de Nane)
async def callback_corregir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split(":", 2)
    notion_id = data[1]
    concepto = data[2] if len(data) > 2 else "Gasto"

    context.user_data["gasto_corregir"] = {
        "notion_id": notion_id,
        "concepto": concepto
    }

    opciones = [
        ["Restaurantes", "Super"],
        ["Abarrotes", "Gasolina"],
        ["Servicios", "Treat"],
        ["Salidas", "Streaming"],
        ["Luz", "Seguro Auto"],
        ["Otros", "Carniceria"],
    ]
    await query.message.reply_text(
        f"Corriendo: {concepto}\n\nElige la nueva subcategoria:",
        reply_markup=ReplyKeyboardMarkup(opciones, one_time_keyboard=True, resize_keyboard=True)
    )
    return CORREGIR_CATEGORIA

# HANDLERS PRINCIPALES
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        await update.message.reply_text("No tienes acceso.")
        return
    await update.message.reply_text(
        "Hola! Soy tu bot de gastos.\n\n"
        "Escríbeme: Concepto Monto\n\n"
        "Comandos:\n"
        "/corregir - Corregir categoria de un gasto reciente\n\n"
        "Ejemplos:\n"
        "Starbucks 150\n"
        "Gasolina 500 BBVA05\n"
        "Walmart 350 ayer\n"
        "Netflix 299 HEYB25\n\n"
        "Tarjetas: BBVA05, BBVA12, HEYB25, BMEX04, EFVO"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END

    texto = update.message.text.strip()
    try:
        gasto = parsear_mensaje(texto)

        if gasto["monto"] >= MONTO_INUSUAL:
            context.user_data["gasto_pendiente"] = gasto
            await update.message.reply_text(
                f"El monto ${gasto['monto']:,.2f} es inusual.\n"
                f"Confirmas el gasto de {gasto['concepto']}?",
                reply_markup=ReplyKeyboardMarkup([["SI", "NO"]], one_time_keyboard=True, resize_keyboard=True)
            )
            return CONFIRMAR_MONTO

        if not gasto["seguro"]:
            context.user_data["gasto_pendiente"] = gasto
            opciones = [
                ["Restaurantes", "Super"],
                ["Abarrotes", "Gasolina"],
                ["Servicios", "Treat"],
                ["Salidas", "Otros"]
            ]
            await update.message.reply_text(
                f"No reconoci bien '{gasto['concepto']}'.\nEn que categoria va?",
                reply_markup=ReplyKeyboardMarkup(opciones, one_time_keyboard=True, resize_keyboard=True)
            )
            return CONFIRMAR_CATEGORIA

        guardado, notion_id, _ = guardar_en_notion(gasto)
        if guardado:
            await enviar_y_notificar(update, context, gasto, notion_id)
        else:
            await update.message.reply_text("Error al guardar en Notion.")

    except ValueError as e:
        await update.message.reply_text(f"{e}\n\nEjemplo: Starbucks 150")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

    return ConversationHandler.END

async def confirmar_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    respuesta = update.message.text.strip().upper()
    gasto = context.user_data.get("gasto_pendiente")
    if respuesta == "SI" and gasto:
        guardado, notion_id, _ = guardar_en_notion(gasto)
        if guardado:
            await enviar_y_notificar(update, context, gasto, notion_id)
        else:
            await update.message.reply_text("Error al guardar.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Gasto cancelado.", reply_markup=ReplyKeyboardRemove())
    context.user_data.pop("gasto_pendiente", None)
    return ConversationHandler.END

async def confirmar_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categoria = update.message.text.strip()
    gasto = context.user_data.get("gasto_pendiente")
    if not gasto:
        await update.message.reply_text("Error.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    CATEGORIA_PRESUPUESTO = {
        "Restaurantes": "Restaurantes", "Super": "Despensa",
        "Abarrotes": "Despensa", "Gasolina": "Automovil",
        "Servicios": "Servicios", "Treat": "Diversión",
        "Salidas": "Diversión", "Otros": "Otros",
    }
    gasto["subcategoria"] = categoria
    gasto["presupuesto"] = CATEGORIA_PRESUPUESTO.get(categoria, "Otros")

    # Guardar aprendizaje
    guardar_en_aprendizaje(gasto["concepto"].lower(), categoria, gasto["presupuesto"])

    guardado, notion_id, _ = guardar_en_notion(gasto)
    if guardado:
        await enviar_y_notificar(update, context, gasto, notion_id)
    else:
        await update.message.reply_text("Error al guardar.", reply_markup=ReplyKeyboardRemove())

    context.user_data.pop("gasto_pendiente", None)
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# SERVIDOR HTTP
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")
        self.wfile.flush()
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"Servidor HTTP en puerto {port}")
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def main():
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()

    app = Application.builder().token(TELEGRAM_TOKEN).job_queue(None).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
            CommandHandler("corregir", cmd_corregir),
            CallbackQueryHandler(callback_corregir, pattern="^corregir:"),
        ],
        states={
            CONFIRMAR_MONTO:     [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_monto)],
            CONFIRMAR_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_categoria)],
            CORREGIR_ELEGIR:     [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_elegir)],
            CORREGIR_CATEGORIA:  [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_categoria)],
            CORREGIR_PRESUPUESTO:[MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_presupuesto)],
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    print("Bot corriendo con correccion y aprendizaje...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
