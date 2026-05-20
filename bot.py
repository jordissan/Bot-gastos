import os, re, datetime, requests, threading, unicodedata, json, logging, time, base64, zoneinfo, asyncio
from difflib import SequenceMatcher
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN        = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN          = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID    = os.environ["NOTION_DATABASE_ID"]
NOTION_APRENDIZAJE_ID = "3ba6f37c717948a1a6aeac3b384ff33c"
NOTION_HISTORIAL_ID   = "35f7eb0cbb9280ae8f02f69b4f242298"
GOOGLE_MAPS_API_KEY   = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", "")
WEBHOOK_SECRET        = os.environ.get("WEBHOOK_SECRET", "")
RENDER_EXTERNAL_URL   = os.environ.get("RENDER_EXTERNAL_URL", "")
NOTION_BALANCE_ID     = os.environ.get("NOTION_BALANCE_ID", "")
GROQ_API_KEY          = os.environ.get("GROQ_API_KEY", "")

# ── GROQ LLM ──────────────────────────────────────────────────────────────────
_groq_client = None

def get_groq():
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=GROQ_API_KEY)
            logger.info("Groq (Llama 3.3 70B) inicializado correctamente")
        except Exception as e:
            logger.error(f"Error inicializando Groq: {e}")
    return _groq_client

def groq_completar(prompt: str, max_tokens: int = 300):
    """Llamada síncrona a Groq (texto). Retorna el texto generado o None si falla."""
    client = get_groq()
    if not client:
        return None
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq texto error: {e}")
        return None

def groq_vision(image_bytes: bytes, prompt: str, max_tokens: int = 200):
    """Llamada síncrona a Groq con imagen (Llama 4 Scout). Retorna texto o None si falla."""
    client = get_groq()
    if not client:
        return None
    try:
        img_b64 = base64.b64encode(image_bytes).decode()
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq vision error: {e}")
        return None

# ── CONTEXTO DE CONVERSACION ──────────────────────────────────────────────────
# Guarda el último gasto guardado por usuario para ediciones contextuales
_ultimo_gasto_usuario = {}

def guardar_contexto(user_id: int, gasto: dict):
    """Guarda el último gasto completo del usuario para uso contextual."""
    _ultimo_gasto_usuario[user_id] = gasto.copy()

def obtener_contexto(user_id: int):
    return _ultimo_gasto_usuario.get(user_id)

USUARIOS_AUTORIZADOS = {8663298433, 8093171397}
USUARIOS_NOMBRES     = {8663298433: "Jordi", 8093171397: "Nani"}
USUARIOS_NOTIFICAR   = {8663298433: 8093171397, 8093171397: 8663298433}

MONTO_INUSUAL    = 5000
CONFIRMAR_MONTO  = 1
CONFIRMAR_CAT    = 2
CONFIRMAR_SUBCAT = 3
CORREGIR_ELEGIR  = 10
CORREGIR_QUE     = 11
CORREGIR_CAT_GRP = 12
CORREGIR_SUBCAT  = 13
CORREGIR_PRESU   = 14
CORREGIR_MONTO   = 15
PRUEBA_GASTO     = 20
FOTO_CONFIRMAR   = 30
ELIMINAR_CONFIRM = 50

SC = {
    "Super":"bf7d4b7d0445441ab89b53eec946d028","Abarrotes":"3587eb0cbb9280c58919c55b065c1e19",
    "Carniceria":"6a734da3d457465db419f195de13909b","Mercado":"3587eb0cbb9280c58919c55b065c1e19",
    "Comida":"3587eb0cbb9280c58919c55b065c1e19","Restaurantes":"1cf748f0639e41469ae2cc73aa86e10a",
    "Gasolina":"8382b85617f342afa50ed56ca48ed9d3","Estacionamento":"31ce3fef973e47bb95259d253817a417",
    "Mantenimiento":"50eae9bd7c3f4cf78f02eae174dedc25","VW POLO":"1fa7eb0cbb928068a523f7a0b9cbb0a3",
    "Servicios":"b4d2856cb9a44fd584904aabcc007008","Streaming":"1d87eb0cbb9280a186f9f369501da604",
    "Internet":"8351d13e3b2e4bdcbfa0bcc97c0392bc","Telefonia Celular":"7a0ff69980f14b22b1767b7e826d33e3",
    "Luz":"bf545e8169f840eda0ca126164e105b8","Agua":"80ff78e25af04952a90ffbc6e452c84f",
    "Renta":"31382e5d307f455aa540b5ee422d5046","Seguro Auto":"cf81abcd84824b82b71455913fefdd2a",
    "Treat":"1d87eb0cbb9280d5b5b0e9efd29e46bf","Salidas":"1d87eb0cbb9280c1b4b7d3beeb2b1ebc",
    "Cine":"1fa484da9e2d4777ab1521d9c34abb60","Conciertos":"b8581fd6ac0d48cbad91890377ab642d",
    "Tiempo de calidad":"ee047ce5151d4300a02c08cf44c273c8","Ropa":"6447d4fe109a431abc217d04f54ba91d",
    "Calzado":"77e1d9b686054539a2d052cbcbf6f341","Doctor":"59148339aab54dd0a1f3b315bfc6a521",
    "Medicina":"d495413562a848cc89710e90a32219e0","Gimnasio":"f0bba54f0eca44f2a9ddca61d1218e57",
    "Corte de pelo":"20e58a92053f4084b149d158c217ff96","Cuidado personal":"7287cad9f27040dca2149a1da0e9d03c",
    "Gasto personal":"1d87eb0cbb928065a2fcddcc3de0cdd8","Muebles":"cb6257b088fc443ea512b14a8a4d9a95",
    "Decoracion":"cee5039a07bf45fe941ea71f0e570335","Libros":"931ebc757b6d4b60908a113684546862",
    "Cursos":"5acc85e7ac924174a21f0b93e44ec0ed","Emergencias":"980640dd649642f5bdd9c8a11ba2ea03",
    "Ezra":"2457eb0cbb92806eaff7c989e5ccfe34","Regalos":"ced98b7c20b74ada88bc087489c4e7bd",
    "Ofrenda":"3e2ae6fbd5024e4f9bb44acc35167eda","Diezmo":"e9517e40830f45eaa46a1f6f1b496daf",
    "Otros":"fd99fde0fa724f41a0ffeb7ee9425ec8","MSI":"1fa7eb0cbb928050a619e2105a4b77e4",
    "Deudas":"583b7dd3eb694921ac327e66821dd715","EFI":"3597eb0cbb9280d79e1bf0e8f7de7f6d",
    "DBMEX":"3597eb0cbb92803f8a8bd99d09450717","PDHB25":"3597eb0cbb9281b3a935f46cdba3333c",
    "PRP":"1fb7eb0cbb9280198a32ec4395b6de35","Impuestos":"56681551d6044dddbf918ced2761b465",
    "Vacaciones":"82c84acd15304f50a33deefad78ec711",
}

PR = {
    "Despensa":"0e4bbd6e13b34972b39f14f76eb61d7d","Diversión":"a1d0605a28694b0baefdc43ac75a798a",
    "Servicios":"0a9ef564f8944cc088e302e64ad702b6","Automovil":"20f5ab24f9ca4185af6a34254ab3a630",
    "Restaurantes":"3547eb0cbb9281e08ef5f3666e091a44","Salud":"3547eb0cbb9281a1ba5dfea0791b8d36",
    "Deuda":"91ab43856d1e4ae69f21f4203eeb3c54","MSI":"1fc7eb0cbb92802ba323cfc943dc0f2c",
    "Renta":"eeb6e04137c248468f641a5044b16545","Ezra":"3547eb0cbb92817baaa9f6681e6bbabc",
    "Cuidado personal":"829161723b0b49bf8787663a89c7248d","Vacaciones":"545753674d4e4d0ca0fd8be7d33db21e",
    "Impuestos":"224cdb40f1f749c7b5d6e165ad31110d","Entretenimiento":"3547eb0cbb92815d8248db75a759646b",
    "Generosidad":"f4cac9f4b95e4508942ad02ae69ddffe","Iglesia":"89b897bd6fa24b8d897adf380491130e",
    "Personal":"3c42302c396c4f4abffa38bff79ccac6","Departamento":"1af955c917f54a2da39e9bbb8e4032ff",
    "Otros":"1ea7eb0cbb9280cbbe43c1bd54396691",
}

PR_EMOJI = {
    "Despensa":"🛒","Diversión":"🎉","Servicios":"🧾","Automovil":"🚗",
    "Restaurantes":"🍽️","Salud":"💊","Deuda":"🏦","MSI":"💳",
    "Renta":"🏠","Ezra":"👶","Cuidado personal":"💆","Vacaciones":"🏖️",
    "Impuestos":"📊","Entretenimiento":"🎭","Generosidad":"🤝","Iglesia":"⛪",
    "Personal":"👤","Departamento":"🏡","Otros":"📦",
}

# Emojis que ocupan 1 celda en monoespaciado (en vez de 2) — necesitan espacio extra
EMOJI_ESTRECHO = {"⛪"}  # Servicios cambió a 💡 (full-width); solo ⛪ sigue siendo angosto

NOTION_API_BASE    = "https://api.notion.com/v1"
NOTION_T_SHORT     = 5
NOTION_T_DEFAULT   = 8
NOTION_T_LONG      = 15

# ── HELPERS ──────────────────────────────────────────────────────────────────
def normalizar(t):
    t=t.lower().strip(); t=unicodedata.normalize("NFD",t)
    return "".join(c for c in t if unicodedata.category(c)!="Mn")

def similitud(a,b): return SequenceMatcher(None,normalizar(a),normalizar(b)).ratio()
def nh(): return {"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"}

def notion_rich_text(props: dict, campo: str) -> str:
    rt = props.get(campo, {}).get("rich_text", [])
    return rt[0]["text"]["content"] if rt else ""

def notion_deep_link(page_id: str) -> str:
    pid = page_id.replace("-", "")
    return f"https://www.notion.so/{pid}"

# ── REINTENTOS ───────────────────────────────────────────────────────────────
def notion_request(method, url, **kwargs):
    intentos = 3
    for i in range(intentos):
        try:
            r = requests.request(method, url, **kwargs)
            if r.status_code < 500:
                return r
            logger.warning(f"Notion error {r.status_code}, intento {i+1}/{intentos}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Notion request exception: {e}, intento {i+1}/{intentos}")
        if i < intentos - 1:
            time.sleep(2)
    return None

def query_notion_db(database_id: str, filter_dict: dict = None) -> list:
    results, cursor = [], None
    body = {"page_size": 100}
    if filter_dict:
        body["filter"] = filter_dict
    while True:
        if cursor:
            body["start_cursor"] = cursor
        r = notion_request("POST", f"{NOTION_API_BASE}/databases/{database_id}/query",
                           headers=nh(), json=body, timeout=NOTION_T_LONG)
        if not r or r.status_code != 200:
            break
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results

# ── CACHE DE MESES ────────────────────────────────────────────────────────────
_meses_cache: dict = {}

def precargar_meses():
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado — meses no precargados")
        return
    try:
        r = requests.post(
            f"{NOTION_API_BASE}/databases/{NOTION_BALANCE_ID}/query",
            headers=nh(), json={"page_size": 50}, timeout=NOTION_T_LONG)
        if r.status_code == 200:
            for page in r.json().get("results", []):
                for prop_val in page.get("properties", {}).values():
                    if prop_val.get("type") == "title":
                        title_list = prop_val.get("title", [])
                        nombre = title_list[0]["text"]["content"] if title_list else ""
                        if nombre:
                            _meses_cache[nombre] = page["id"]
            logger.info(f"Cache de meses cargado: {list(_meses_cache.keys())}")
        else:
            logger.error(f"Error precargando meses: {r.status_code} {r.text[:100]}")
    except Exception as e:
        logger.error(f"Error precargando meses: {e}")

def buscar_mes_id(mes: str):
    if mes in _meses_cache:
        return _meses_cache[mes]
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado")
        return None
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_BALANCE_ID}/query",
            headers=nh(), json={"page_size": 50}, timeout=NOTION_T_LONG)
        if r and r.status_code == 200:
            for page in r.json().get("results", []):
                for prop_val in page.get("properties", {}).values():
                    if prop_val.get("type") == "title":
                        title_list = prop_val.get("title", [])
                        nombre = title_list[0]["text"]["content"] if title_list else ""
                        if nombre:
                            _meses_cache[nombre] = page["id"]
            if mes in _meses_cache:
                logger.info(f"Mes {mes} encontrado: {_meses_cache[mes]}")
                return _meses_cache[mes]
            logger.error(f"Mes {mes} no encontrado en BD Balance")
        else:
            logger.error(f"Error consultando BD Balance: {r.status_code if r else 'sin respuesta'}")
    except Exception as e:
        logger.error(f"Error en buscar_mes_id({mes}): {e}")
    return None

# ── MES ACTIVO ────────────────────────────────────────────────────────────────
MESES_ESP = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}

def mes_activo_str() -> str:
    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    if hoy.day >= 5:
        if hoy.month == 12:
            y, m = hoy.year + 1, 1
        else:
            y, m = hoy.year, hoy.month + 1
    else:
        y, m = hoy.year, hoy.month
    return f"{MESES_ESP[m]}{str(y)[-2:]}"

def fila_tabla(nombre: str, monto: float, nom_pad: int, extra: str = "") -> str:
    emoji = PR_EMOJI.get(nombre, "📦")
    e_str = emoji + " " if emoji in EMOJI_ESTRECHO else emoji
    monto_s = f"${monto:,.0f}".rjust(9)
    return f"{e_str} {nombre.ljust(nom_pad)}  {monto_s}{extra}"

# ── RESUMEN ───────────────────────────────────────────────────────────────────
async def cmd_resumen(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return

    args = context.args
    mes = args[0].upper() if args else mes_activo_str()

    mid = buscar_mes_id(mes)
    if not mid:
        await update.message.reply_text(f"❌ No encontré el mes {mes} en Notion.")
        return

    await update.message.reply_text(f"⏳ Calculando resumen de {mes}...")

    gastos = query_notion_db(NOTION_DATABASE_ID,
                             {"property": "Mes", "relation": {"contains": mid}})
    if not gastos:
        await update.message.reply_text(f"📭 No hay gastos registrados en {mes}.")
        return

    # Agrupar por presupuesto — normalizar ID quitando guiones
    totales = {}
    for g in gastos:
        props = g.get("properties", {})
        monto = props.get("Monto", {}).get("number", 0) or 0
        rel_pre = props.get("Presupuesto", {}).get("relation", [])
        if rel_pre:
            pr_id = rel_pre[0].get("id", "").replace("-", "")
            pr_nombre = next((k for k, v in PR.items() if v == pr_id), None)
        else:
            pr_nombre = None
        if pr_nombre:
            totales[pr_nombre] = totales.get(pr_nombre, 0) + monto

    if not totales:
        await update.message.reply_text(f"📭 No hay gastos con presupuesto asignado en {mes}.")
        return

    # Ordenar de mayor a menor
    ordenados = sorted(totales.items(), key=lambda x: x[1], reverse=True)
    total_general = sum(t for _, t in ordenados)

    # Construir tabla monoespaciada con padding
    # Los emojis estrechos reciben un espacio extra para compensar su ancho de 1 celda
    max_nom = max(len(n) for n, _ in ordenados)
    tabla = []
    for nombre, monto in ordenados:
        pct   = round((monto / total_general) * 100) if total_general else 0
        tabla.append(fila_tabla(nombre, monto, max_nom, f"  {pct}%".rjust(5)))

    msg = (
        f"📊 *Resumen {mes}*\n\n"
        f"```\n\n{chr(10).join(tabla)}\n```\n\n"
        f"💰 *Total*   ${total_general:,.0f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ── CONCEPTOS UNIVOCOS ────────────────────────────────────────────────────────
CONCEPTOS_UNIVOCOS = {
    "netflix","spotify","disney","hbo","apple tv","paramount","crunchyroll",
    "max","prime video","izzi","telmex","adobe","icloud","capcut","claude",
    "figma","canva","microsoft","chatgpt","at&t","att","cfe","mapfre",
    "seguro auto","qualitas","walmart","soriana","bodega aurrera","oxxo gas","oxxogas",
    "sam's","chedraui","zarapes",
    "google one","disney+","hbo max","apple one","youtube premium","paramount+",
    "shein","mercado libre","amazon prime","uber","didi",
}

def es_concepto_univoco(concepto: str) -> bool:
    c = normalizar(concepto)
    return any(normalizar(u) in c for u in CONCEPTOS_UNIVOCOS)

# ── GRUPOS / MENUS ───────────────────────────────────────────────────────────
GRUPOS_CAT = {
    "🚗 Automovil":    ["Gasolina","Estacionamento","Mantenimiento","VW POLO","Seguro Auto"],
    "👤 Personal":     ["Ropa","Calzado","Doctor","Medicina","Gimnasio","Corte de pelo","Cuidado personal","Gasto personal"],
    "🛒 Despensa":     ["Super","Abarrotes","Carniceria","Mercado","Comida"],
    "🏦 Deudas":       ["MSI","Deudas","EFI","DBMEX","PDHB25","PRP","Impuestos"],
    "🎉 Diversión":    ["Salidas","Treat","Cine","Conciertos","Tiempo de calidad"],
    "📚 Educación":    ["Libros","Cursos"],
    "🚨 Emergencias":  ["Emergencias"],
    "👶 Ezra":         ["Ezra"],
    "🤝 Generosidad":  ["Regalos","Ofrenda","Diezmo"],
    "⛪ Iglesia":      ["Iglesia"],
    "📦 Otros":        ["Otros","Vacaciones"],
    "🍽️ Restaurantes": ["Restaurantes"],
    "⚡ Servicios":    ["Servicios","Streaming","Internet","Telefonia Celular","Luz","Agua"],
    "🏠 Departamento": ["Renta","Muebles","Decoracion"],
}

BTN_CANCELAR = "❌ Cancelar"
BTN_REGRESAR = "⬅️ Regresar"

def menu_grupos():
    return [
        ["🚗 Automovil",   "👤 Personal"],
        ["🛒 Despensa",    "🏦 Deudas"],
        ["🎉 Diversión",   "📚 Educación"],
        ["🚨 Emergencias", "👶 Ezra"],
        ["🤝 Generosidad", "⛪ Iglesia"],
        ["📦 Otros",       "🍽️ Restaurantes"],
        ["⚡ Servicios",   "🏠 Departamento"],
        [BTN_REGRESAR,     BTN_CANCELAR],
    ]

def menu_presupuesto():
    return [
        ["🛒 Despensa",        "🎉 Diversión"],
        ["⚡ Servicios",       "🚗 Automovil"],
        ["🍽️ Restaurantes",   "💊 Salud"],
        ["🏦 Deuda",           "💳 MSI"],
        ["🏠 Renta",           "👶 Ezra"],
        ["💆 Cuidado personal","🏖️ Vacaciones"],
        ["📊 Impuestos",       "🎭 Entretenimiento"],
        ["🤝 Generosidad",     "⛪ Iglesia"],
        ["👤 Personal",        "🏡 Departamento"],
        ["📦 Otros"],
        [BTN_REGRESAR,         BTN_CANCELAR],
    ]

def menu_que_corregir():
    return [
        ["🏷️ Subcategoría", "💰 Presupuesto"],
        ["✏️ Ambas",        "💵 Monto"],
        [BTN_REGRESAR,      BTN_CANCELAR],
    ]

def menu_elegir(ultimos):
    filas = [[f"{i+1}"] for i in range(len(ultimos))]
    filas.append([BTN_CANCELAR])
    return filas

def limpiar_emoji(texto):
    t = texto.strip()
    partes = t.split(" ", 1)
    if len(partes) == 2 and len(partes[0]) <= 3:
        return partes[1]
    return t

def grupo_key(texto):
    t = texto.strip()
    for grp in GRUPOS_CAT:
        if t == grp: return grp
        if limpiar_emoji(t) == limpiar_emoji(grp): return grp
    return t

def presu_limpio(texto):
    return limpiar_emoji(texto.strip())

REGLAS_CONCEPTO = [
    (["walmart","soriana","costco","bodega aurrera","bae ","chedraui","sam's"],"Super","Despensa"),
    (["calii"],"Super","Despensa"),
    (["zarapes","merpago*zarapes"],"Restaurantes","Despensa"),
    (["carniceria","carnes especiales","barrangueno","pescaderia","altamez"],"Carniceria","Despensa"),
    (["restaurante","taqueria","tacos","pizza","sushi","pollo bronco","dq ","dairy queen","carl's","mcdonald","burger","kfc","subway","domino","clip mx*rest","payclip*rest","la choco","mamma farina","dolce natura","los elotis","punto sur","barbacos","barbacoa","velma","calena","bistro","meridiao","uber eats","rappi"],"Restaurantes","Restaurantes"),
    (["oxxo gas","oxxogas","oxxo gaspaseos","gasolina","bp ","shell ","petro","combustible"],"Gasolina","Automovil"),
    (["netflix","spotify","disney","hbo","apple tv","paramount","crunchyroll","max ","prime video"],"Streaming","Servicios"),
    (["izzi","telmex","adobe","icloud","capcut","claude","conekta*parco","figma","canva","microsoft","chatgpt"],"Servicios","Servicios"),
    (["google"],"Servicios","Servicios"),
    (["at&t","att "],"Telefonia Celular","Servicios"),
    (["cfe"],"Luz","Servicios"),
    (["mapfre","seguro auto","qualitas"],"Seguro Auto","Automovil"),
    (["autolavado","refaccion","mecanico","llantas"],"Mantenimiento","Automovil"),
    (["farmacia guadalajara","farmacia benavides","farmacias del ahorro","farmacia similares","farmacia"],"Medicina","Personal"),
    (["doctor","hospital","clinica","medico","consulta"],"Doctor","Personal"),
    (["gerber","nutrileche","pedialyte"],"Ezra","Ezra"),
    (["oxxo","naranjitas","rancherita","super rancherita","abarrotes","minisuper","seven","mercado ","barreto","merpago*abarrotes"],"Abarrotes","Despensa"),
    (["parco","conekta*parco","estacionamiento"],"Estacionamento","Automovil"),
    (["cinepolis","cinemex","cine "],"Cine","Diversión"),
    (["teatro","concierto","evento","antro","bar "],"Salidas","Diversión"),
    (["starbucks","cafe ","coffee","brüm","brum","helado","nieve","nieves","paleta","panaderia","pasteleria"],"Treat","Diversión"),
    (["amazon"],"Otros","Otros"),
    (["uber","didi","cabify"],"Gasolina","Automovil"),
]

MESES_TEXTO = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,
               "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,
               "septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}

# ── GOOGLE VISION OCR ─────────────────────────────────────────────────────────
def ocr_ticket(image_bytes: bytes) -> str:
    if not GOOGLE_VISION_API_KEY:
        logger.warning("GOOGLE_VISION_API_KEY no configurado")
        return ""
    try:
        payload = {
            "requests": [{
                "image": {"content": base64.b64encode(image_bytes).decode()},
                "features": [{"type": "TEXT_DETECTION", "maxResults": 1}]
            }]
        }
        r = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}",
            json=payload, timeout=NOTION_T_DEFAULT)
        if r.status_code == 200:
            anotaciones = r.json().get("responses", [{}])[0].get("textAnnotations", [])
            if anotaciones:
                return anotaciones[0].get("description", "")
        else:
            logger.error(f"Vision API error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Error en ocr_ticket: {e}")
    return ""

# Comercios reconocibles en el texto OCR → concepto limpio (que luego pasa a inferir_categoria)
COMERCIOS_OCR = {
    "walmart":"Walmart","bodega aurrera":"Bodega Aurrera","soriana":"Soriana","chedraui":"Chedraui",
    "costco":"Costco","sam's":"Sam's Club","sams club":"Sam's Club","la comer":"La Comer","heb":"HEB",
    "oxxo gas":"Oxxo Gas","oxxo":"Oxxo","7 eleven":"Seven","7-eleven":"Seven","seven eleven":"Seven",
    "home depot":"Home Depot","liverpool":"Liverpool","coppel":"Coppel","sears":"Sears",
    "farmacia guadalajara":"Farmacia Guadalajara","farmacias del ahorro":"Farmacias del Ahorro",
    "farmacia benavides":"Farmacia Benavides","farmacias similares":"Farmacia Similares",
    "starbucks":"Starbucks","mcdonald":"McDonalds","burger king":"Burger King","kfc":"KFC",
    "subway":"Subway","domino":"Dominos","little caesar":"Little Caesars","carls jr":"Carl's Jr",
    "uber eats":"Uber Eats","rappi":"Rappi","cinepolis":"Cinepolis","cinemex":"Cinemex",
    "shell":"Shell","pemex":"Pemex","bp ":"BP","mobil":"Mobil",
}

# Palabras que invalidan un "TOTAL" como monto (es conteo, no importe)
_TOTAL_FALSO = re.compile(r'(ARTICULO|PIEZA|PRODUCTO|ITEM|UNIDAD|CANT)', re.IGNORECASE)
# Monto con 2 decimales: 1,234.56 / 234.56 / 1234.56
_RE_MONEY = re.compile(r'\$?\s*(\d{1,3}(?:[,]?\d{3})*\.\d{2})')
# Palabras clave de total, con prioridad (mayor = más confiable)
_KW_TOTAL = [
    (re.compile(r'TOTAL\s*A\s*PAGAR', re.I), 5),
    (re.compile(r'IMPORTE\s*TOTAL',   re.I), 4),
    (re.compile(r'\bTOTAL\b',          re.I), 3),
    (re.compile(r'A\s*PAGAR',          re.I), 3),
    (re.compile(r'\bIMPORTE\b',        re.I), 2),
]

def _monto_de_linea(linea: str):
    m = _RE_MONEY.search(linea)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except (ValueError, TypeError):
        return None

def parsear_ticket(texto: str) -> dict:
    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]

    # ── MONTO ── prioriza línea con palabra clave de total; a igual prioridad, la de más abajo
    mejor = None  # (prioridad, indice, monto)
    for idx, linea in enumerate(lineas):
        if _TOTAL_FALSO.search(linea):
            continue
        val = _monto_de_linea(linea)
        if val is None:
            continue
        for patron, prio in _KW_TOTAL:
            if patron.search(linea):
                if mejor is None or (prio, idx) > (mejor[0], mejor[1]):
                    mejor = (prio, idx, val)
                break
    monto = mejor[2] if mejor else None
    # Fallback: el monto con 2 decimales más grande de todo el ticket
    if monto is None:
        montos = [v for l in lineas if (v := _monto_de_linea(l)) is not None]
        if montos:
            monto = max(montos)

    # ── FECHA ──
    fecha = hoy
    for patron in (r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})'):
        m = re.search(patron, texto)
        if m:
            try:
                g = m.groups()
                if len(g[0]) == 4:
                    y, mo, d = int(g[0]), int(g[1]), int(g[2])
                else:
                    d, mo, y = int(g[0]), int(g[1]), int(g[2])
                    if y < 100: y += 2000
                fecha = datetime.date(y, mo, d)
                break
            except (ValueError, TypeError): pass

    # ── CONCEPTO ── 1) comercio conocido en el texto  2) primera línea limpia del encabezado
    texto_norm = normalizar(texto)
    concepto = None
    for clave, nombre in COMERCIOS_OCR.items():
        if normalizar(clave) in texto_norm:
            concepto = nombre
            break
    if not concepto:
        for linea in lineas[:6]:
            if len(linea) < 3: continue
            if re.search(r'\d{3,}', linea): continue                       # folios, RFC, teléfonos
            if re.match(r'^[\d\s\$\.\,\-\*\/\:#]+$', linea): continue       # solo símbolos/números
            if re.match(r'^(RFC|TEL|FOLIO|TICKET|CAJA|SUCURSAL|FECHA|HORA|CP|NO\b)', linea, re.I): continue
            concepto = linea.title()
            break
    if not concepto:
        concepto = "Ticket"

    return {"concepto": concepto, "monto": monto, "fecha": fecha}

def analizar_ticket_groq(image_bytes: bytes):
    """
    Analiza una foto de ticket con Llama 4 Scout y extrae concepto, monto y fecha.
    Reemplaza el flujo ocr_ticket() + parsear_ticket().
    Retorna dict con las mismas claves que parsear_ticket(), o None si falla.
    """
    if not GROQ_API_KEY:
        return None

    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()

    prompt = f"""Analiza este ticket o recibo de compra y extrae los datos principales. Hoy es {hoy.strftime('%d/%m/%Y')}.

Responde SOLO con JSON válido, sin texto adicional, sin markdown:
{{
  "concepto": "nombre del comercio en Title Case (ej: Walmart, Oxxo, Starbucks)",
  "monto": número con decimales (el TOTAL A PAGAR final, no subtotal ni total de artículos),
  "fecha": "YYYY-MM-DD"
}}

Reglas:
- El monto debe ser el total final que se pagó, incluyendo IVA.
- Si hay varios totales, elige el mayor que sea claramente el total de la compra.
- Si no puedes leer la fecha, usa {hoy.strftime('%Y-%m-%d')}.
- Si no reconoces el comercio, describe brevemente qué tipo de negocio es."""

    raw = groq_vision(image_bytes, prompt, max_tokens=150)
    if not raw:
        return None

    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)

        concepto = data.get("concepto", "").strip()
        monto = data.get("monto")
        fecha_str = data.get("fecha", hoy.strftime("%Y-%m-%d"))

        if not concepto or monto is None:
            return None

        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = hoy

        return {"concepto": concepto.title(), "monto": float(monto), "fecha": fecha}
    except Exception as e:
        logger.warning(f"Groq ticket fallido: {e}")
        return None

# ── APRENDIZAJE ──────────────────────────────────────────────────────────────
def _buscar_entrada_aprendizaje(concepto: str):
    r = notion_request("POST", f"{NOTION_API_BASE}/databases/{NOTION_APRENDIZAJE_ID}/query",
                       headers=nh(),
                       json={"filter": {"property": "Concepto", "title": {"equals": concepto.lower()}}},
                       timeout=NOTION_T_SHORT)
    if r and r.status_code == 200:
        res = r.json().get("results", [])
        if res:
            return res[0]["id"], res[0]["properties"].get("Usos", {}).get("number", 0) or 0
    return None, 0

def buscar_aprendizaje(concepto):
    r = notion_request("POST",
        f"{NOTION_API_BASE}/databases/{NOTION_APRENDIZAJE_ID}/query",
        headers=nh(),
        json={"filter":{"property":"Concepto","title":{"equals":concepto.lower()}}},
        timeout=NOTION_T_SHORT)
    if r and r.status_code == 200:
        res = r.json().get("results", [])
        if res:
            p = res[0]["properties"]
            s = p.get("Subcategoria",{}).get("rich_text",[])
            b = p.get("Presupuesto",{}).get("rich_text",[])
            if s and b: return s[0]["text"]["content"], b[0]["text"]["content"]
    return None, None

def guardar_aprendizaje(concepto, sub, pre):
    if es_concepto_univoco(concepto):
        return
    hoy = datetime.date.today().isoformat()
    pid, usos = _buscar_entrada_aprendizaje(concepto)
    if pid:
        notion_request("PATCH", f"{NOTION_API_BASE}/pages/{pid}",
            headers=nh(),
            json={"properties": {
                "Subcategoria": {"rich_text": [{"text": {"content": sub}}]},
                "Presupuesto":  {"rich_text": [{"text": {"content": pre}}]},
                "Usos":         {"number": usos + 1},
                "Fecha":        {"date": {"start": hoy}},
            }}, timeout=NOTION_T_SHORT)
        return
    notion_request("POST", f"{NOTION_API_BASE}/pages",
        headers=nh(),
        json={"parent": {"database_id": NOTION_APRENDIZAJE_ID}, "properties": {
            "Concepto":    {"title":     [{"text": {"content": concepto.lower()}}]},
            "Subcategoria":{"rich_text": [{"text": {"content": sub}}]},
            "Presupuesto": {"rich_text": [{"text": {"content": pre}}]},
            "Usos":        {"number": 1},
            "Fecha":       {"date":   {"start": hoy}},
        }}, timeout=NOTION_T_SHORT)

def limpiar_aprendizaje():
    try:
        hoy = datetime.date.today()
        limite_90 = (hoy - datetime.timedelta(days=90)).isoformat()
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_APRENDIZAJE_ID}/query",
            headers=nh(), json={"page_size":200}, timeout=NOTION_T_DEFAULT)
        if not r or r.status_code != 200: return
        entradas = r.json().get("results", [])
        borradas = 0
        for e in entradas:
            p = e["properties"]
            usos = p.get("Usos",{}).get("number",0) or 0
            fecha_raw = p.get("Fecha",{}).get("date")
            fecha_str = fecha_raw["start"] if fecha_raw else None
            if usos == 1 and fecha_str and fecha_str < limite_90:
                notion_request("PATCH", f"{NOTION_API_BASE}/pages/{e['id']}",
                    headers=nh(), json={"archived": True}, timeout=NOTION_T_SHORT)
                borradas += 1
        if len(entradas) - borradas > 150:
            sobrantes = sorted(entradas, key=lambda e: e["properties"].get("Usos",{}).get("number",0) or 0)
            por_borrar = (len(entradas) - borradas) - 100
            for e in sobrantes[:por_borrar]:
                notion_request("PATCH", f"{NOTION_API_BASE}/pages/{e['id']}",
                    headers=nh(), json={"archived": True}, timeout=NOTION_T_SHORT)
                borradas += 1
        if borradas: logger.info(f"Limpieza aprendizaje: {borradas} entradas eliminadas")
    except Exception as ex:
        logger.error(f"Error en limpiar_aprendizaje: {ex}")

# ── HISTORIAL PERSISTENTE ────────────────────────────────────────────────────
MAX_HISTORIAL = 5

def guardar_historial_notion(gasto, usuario_id):
    try:
        notion_request("POST", f"{NOTION_API_BASE}/pages",
            headers=nh(),
            json={"parent":{"database_id":NOTION_HISTORIAL_ID},"properties":{
                "Concepto":    {"title":[{"text":{"content":gasto["concepto"]}}]},
                "Monto":       {"number":gasto["monto"]},
                "Fecha":       {"date":{"start":gasto["fecha"]}},
                "Tarjeta":     {"rich_text":[{"text":{"content":gasto["tarjeta"]}}]},
                "Mes":         {"rich_text":[{"text":{"content":gasto["mes"]}}]},
                "Subcategoria":{"rich_text":[{"text":{"content":gasto["subcategoria"]}}]},
                "Presupuesto": {"rich_text":[{"text":{"content":gasto["presupuesto"]}}]},
                "NotionID":    {"rich_text":[{"text":{"content":gasto.get("notion_id","")}}]},
                "UsuarioID":   {"number":usuario_id},
            }}, timeout=NOTION_T_SHORT)
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_HISTORIAL_ID}/query",
            headers=nh(),
            json={
                "filter":{"property":"UsuarioID","number":{"equals":usuario_id}},
                "sorts":[{"timestamp":"created_time","direction":"descending"}],
                "page_size": 20,
            }, timeout=NOTION_T_SHORT)
        if r and r.status_code == 200:
            entradas = r.json().get("results",[])
            for vieja in entradas[MAX_HISTORIAL:]:
                notion_request("PATCH", f"{NOTION_API_BASE}/pages/{vieja['id']}",
                    headers=nh(), json={"archived": True}, timeout=NOTION_T_SHORT)
    except Exception as ex:
        logger.error(f"Error guardando historial: {ex}")

def cargar_historial_notion(usuario_id):
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_HISTORIAL_ID}/query",
            headers=nh(),
            json={
                "filter":{"property":"UsuarioID","number":{"equals":usuario_id}},
                "sorts":[{"timestamp":"created_time","direction":"descending"}],
                "page_size": MAX_HISTORIAL,
            }, timeout=NOTION_T_SHORT)
        if r and r.status_code == 200:
            resultado = []
            for e in r.json().get("results",[]):
                p = e["properties"]
                resultado.append({
                    "concepto":    (p.get("Concepto",{}).get("title",[{}])[0].get("text",{}).get("content","") if p.get("Concepto",{}).get("title") else ""),
                    "monto":       p.get("Monto",{}).get("number",0) or 0,
                    "fecha":       (p.get("Fecha",{}).get("date",{}) or {}).get("start",""),
                    "tarjeta":     notion_rich_text(p, "Tarjeta"),
                    "mes":         notion_rich_text(p, "Mes"),
                    "subcategoria":notion_rich_text(p, "Subcategoria"),
                    "presupuesto": notion_rich_text(p, "Presupuesto"),
                    "notion_id":   notion_rich_text(p, "NotionID"),
                })
            return resultado
    except Exception as ex:
        logger.error(f"Error cargando historial: {ex}")
    return []

# ── MAPS ─────────────────────────────────────────────────────────────────────
def buscar_maps(concepto):
    if not GOOGLE_MAPS_API_KEY: return None
    try:
        r=requests.post("https://places.googleapis.com/v1/places:searchText",
            headers={"Content-Type":"application/json","X-Goog-Api-Key":GOOGLE_MAPS_API_KEY,"X-Goog-FieldMask":"places.types"},
            json={"textQuery":f"{concepto} Guadalajara Mexico","locationBias":{"circle":{"center":{"latitude":20.6597,"longitude":-103.3496},"radius":50000.0}}},
            timeout=3)
        if r.status_code==200:
            p=r.json().get("places",[])
            if p: return p[0].get("types",[])
    except Exception as e: logger.warning(f"Maps error buscando '{concepto}': {e}")
    return None

MAPS_TIPOS={"restaurant":("Restaurantes","Restaurantes"),"cafe":("Treat","Diversión"),"bakery":("Treat","Diversión"),
            "supermarket":("Super","Despensa"),"grocery_or_supermarket":("Super","Despensa"),
            "convenience_store":("Abarrotes","Despensa"),"gas_station":("Gasolina","Automovil"),
            "pharmacy":("Medicina","Personal"),"hospital":("Doctor","Personal"),
            "car_wash":("Mantenimiento","Automovil"),"movie_theater":("Cine","Diversión"),
            "night_club":("Salidas","Diversión"),"bar":("Salidas","Diversión")}

def cat_maps(tipos):
    if not tipos: return None,None
    for t in tipos:
        for k,v in MAPS_TIPOS.items():
            if k in t: return v
    return None,None

# ── INFERENCIA ───────────────────────────────────────────────────────────────
def inferir_categoria(concepto):
    c=normalizar(concepto)
    for palabras,sub,pre in REGLAS_CONCEPTO:
        for p in palabras:
            if normalizar(p) in c: return sub,pre,True
    sa,pa=buscar_aprendizaje(concepto)
    if sa: return sa,pa,True
    mejor=0; mejor_r=None
    for palabras,sub,pre in REGLAS_CONCEPTO:
        for p in palabras:
            if len(p)<4: continue
            s=similitud(concepto,p)
            if s>mejor and s>0.80: mejor=s; mejor_r=(sub,pre)
    if mejor_r: return mejor_r[0],mejor_r[1],True
    tipos=buscar_maps(concepto); sm,pm=cat_maps(tipos)
    if sm: return sm,pm,True
    return "Abarrotes","Despensa",False

def inferir_categoria_con_origen(concepto):
    c=normalizar(concepto)
    for palabras,sub,pre in REGLAS_CONCEPTO:
        for p in palabras:
            if normalizar(p) in c: return sub,pre,True,"📋",f"regla: {p}"
    sa,pa=buscar_aprendizaje(concepto)
    if sa: return sa,pa,True,"🧠","aprendizaje"
    mejor=0; mejor_r=None; mejor_p=None
    for palabras,sub,pre in REGLAS_CONCEPTO:
        for p in palabras:
            if len(p)<4: continue
            s=similitud(concepto,p)
            if s>mejor and s>0.80: mejor=s; mejor_r=(sub,pre); mejor_p=p
    if mejor_r: return mejor_r[0],mejor_r[1],True,"🔤",f"similitud con: {mejor_p}"
    tipos=buscar_maps(concepto); sm,pm=cat_maps(tipos)
    if sm: return sm,pm,True,"🗺️","Google Maps"
    return "Abarrotes","Despensa",False,"❓","sin categoría"

# ── TARJETAS Y MESES ─────────────────────────────────────────────────────────
def calcular_tarjeta(fecha,exp=None):
    if exp: return exp.upper()
    return "BBVA05" if 5<=fecha.day<=11 else "BBVA12"

def calcular_mes(fecha,tarjeta):
    d,m,y=fecha.day,fecha.month,fecha.year
    if   tarjeta=="BBVA12": mp=m+1 if d>=12 else m
    elif tarjeta=="BBVA05": mp=m+1 if d>=5  else m
    elif tarjeta=="BMEX04": mp=m+1 if d>=4  else m
    elif tarjeta=="HEYB25": mp=m+2 if d>=25 else m+1
    else: mp=m
    while mp>12: mp-=12; y+=1
    return f"{MESES_ESP[mp]}{str(y)[-2:]}"

# ── PARSEO TEXTO ─────────────────────────────────────────────────────────────
def parsear_fecha(tokens):
    hoy=datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    for i,t in enumerate(tokens):
        tl=t.lower()
        if tl=="ayer": return hoy-datetime.timedelta(days=1),tokens[:i]+tokens[i+1:]
        if tl=="hoy": return hoy,tokens[:i]+tokens[i+1:]
        m=re.match(r'^(\d{1,2})[-/](\d{1,2})$',t)
        if m:
            try: return datetime.date(hoy.year,int(m.group(2)),int(m.group(1))),tokens[:i]+tokens[i+1:]
            except (ValueError, TypeError): pass
        m=re.match(r'^(\d{1,2})[-/]([a-z]+)$',tl)
        if m and m.group(2) in MESES_TEXTO:
            try: return datetime.date(hoy.year,MESES_TEXTO[m.group(2)],int(m.group(1))),tokens[:i]+tokens[i+1:]
            except (ValueError, TypeError): pass
    return hoy,tokens

def parsear_tarjeta(tokens):
    for i,t in enumerate(tokens):
        if t.upper() in ["BBVA05","BBVA12","HEYB25","BMEX04","EFVO"]: return t.upper(),tokens[:i]+tokens[i+1:]
    return None,tokens

def parsear_monto(tokens):
    for i,t in enumerate(tokens):
        try:
            v=float(t.replace("$","").replace(",",""))
            if v>0: return v,tokens[:i]+tokens[i+1:]
        except (ValueError, TypeError): pass
    return None,tokens

def parsear_mensaje(texto):
    tokens=texto.strip().split()
    fecha,tokens=parsear_fecha(tokens); texp,tokens=parsear_tarjeta(tokens); monto,tokens=parsear_monto(tokens)
    concepto=" ".join(tokens).strip()
    if not concepto: raise ValueError("No encontre el concepto")
    if monto is None: raise ValueError("No encontre el monto")
    tarjeta=calcular_tarjeta(fecha,texp); mes=calcular_mes(fecha,tarjeta)
    sub,pre,seguro=inferir_categoria(concepto)
    return {"concepto":concepto.title(),"monto":monto,"fecha":fecha.strftime("%Y-%m-%d"),"tarjeta":tarjeta,"mes":mes,"subcategoria":sub,"presupuesto":pre,"seguro":seguro}

# ── PARSEO CON GROQ (LLM) ─────────────────────────────────────────────────────
def parsear_mensaje_groq(texto: str):
    """
    Intenta parsear un mensaje de gasto usando Groq/Llama 3.3 70B.
    Retorna dict con las mismas claves que parsear_mensaje(), o None si falla.
    El resultado pasa por la misma lógica de tarjeta/mes/categoría que el parser original.
    """
    if not GROQ_API_KEY:
        return None

    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    tarjetas_validas = ["BBVA05", "BBVA12", "HEYB25", "BMEX04", "EFVO"]

    prompt = f"""Extrae los datos de este mensaje de gasto personal escrito en español mexicano informal. Hoy es {hoy.strftime('%d/%m/%Y')}.

Mensaje: "{texto}"

Responde SOLO con JSON válido, sin texto adicional, sin markdown:
{{
  "concepto": "nombre del comercio o descripción corta en Title Case",
  "monto": número (solo dígitos sin signo $),
  "fecha": "YYYY-MM-DD",
  "tarjeta": "una de {tarjetas_validas} o null"
}}

Reglas:
- Si el mensaje NO es un gasto (es pregunta o comando), responde: {{"error": "no_es_gasto"}}
- Concepto conciso: "Starbucks", "Super", "Comida", "Gasolina", etc.
- Si dice "ayer" resta 1 día a la fecha de hoy. Sin fecha mencionada = hoy.
- Montos aproximados ("como 350", "unos 400") → usa ese número.
- Dos montos → usa el mayor (el total)."""

    raw = groq_completar(prompt, max_tokens=120)
    if not raw:
        return None

    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)

        if data.get("error") == "no_es_gasto":
            return None

        concepto = data.get("concepto", "").strip()
        monto = data.get("monto")
        fecha_str = data.get("fecha", hoy.strftime("%Y-%m-%d"))
        tarjeta_raw = data.get("tarjeta")

        if not concepto or monto is None:
            return None

        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = hoy

        tarjeta_exp = tarjeta_raw if tarjeta_raw in tarjetas_validas else None
        tarjeta = calcular_tarjeta(fecha, tarjeta_exp)
        mes = calcular_mes(fecha, tarjeta)
        sub, pre, seguro = inferir_categoria(concepto)

        return {
            "concepto": concepto.title(),
            "monto": float(monto),
            "fecha": fecha.strftime("%Y-%m-%d"),
            "tarjeta": tarjeta,
            "mes": mes,
            "subcategoria": sub,
            "presupuesto": pre,
            "seguro": seguro,
        }
    except Exception as e:
        logger.warning(f"Groq parseo fallido: {e} — texto: {texto[:80]}")
        return None

def _parece_gasto_estricto(texto: str) -> bool:
    """
    Retorna True si el texto ya tiene formato estricto (Concepto Monto [opcional])
    y NO necesita LLM. Ahorra llamadas a la API.
    Ejemplos estrictos: "Oxxo 45", "Starbucks 150 BBVA05", "Super 350 ayer"
    """
    tokens = texto.strip().split()
    if len(tokens) < 2:
        return False
    for t in tokens[-3:]:
        try:
            float(t.replace("$", "").replace(",", ""))
            return True
        except ValueError:
            pass
    return False

def _parece_gasto(texto: str) -> bool:
    """Heurística: ¿el mensaje parece un gasto o una pregunta/consulta?"""
    texto_n = normalizar(texto)
    indicadores_consulta = [
        "cuanto", "cuánto", "cuantos", "cual", "cuál",
        "cuando", "cuándo", "qué tal", "como voy",
        "resumen", "estadistica", "compara", "?",
    ]
    return not any(ind in texto_n for ind in indicadores_consulta)

async def responder_consulta_groq(texto: str, user_id: int, update, context) -> bool:
    """
    Si el mensaje parece una consulta en lenguaje natural, la responde usando Groq
    con datos reales de Notion. Retorna True si respondió, False si no era consulta.
    """
    if not GROQ_API_KEY:
        return False

    mes = mes_activo_str()
    mid = buscar_mes_id(mes)
    resumen_ctx = ""
    if mid:
        try:
            gastos = await asyncio.to_thread(
                query_notion_db, NOTION_DATABASE_ID,
                {"property": "Mes", "relation": {"contains": mid}}
            )
            totales = {}
            for g in gastos:
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                rel_pre = props.get("Presupuesto", {}).get("relation", [])
                if rel_pre:
                    pr_id = rel_pre[0].get("id", "").replace("-", "")
                    pr_nombre = next((k for k, v in PR.items() if v == pr_id), None)
                    if pr_nombre:
                        totales[pr_nombre] = totales.get(pr_nombre, 0) + monto
            if totales:
                lineas = [f"- {k}: ${v:,.0f}" for k, v in sorted(totales.items(), key=lambda x: x[1], reverse=True)]
                resumen_ctx = f"Gastos de {mes}:\n" + "\n".join(lineas)
                resumen_ctx += f"\nTotal: ${sum(totales.values()):,.0f}"
        except Exception as e:
            logger.warning(f"Error obteniendo contexto para consulta: {e}")

    ultimo = obtener_contexto(user_id)
    ultimo_ctx = ""
    if ultimo:
        ultimo_ctx = f"Último gasto: {ultimo['concepto']} ${ultimo['monto']:,.2f} ({ultimo['subcategoria']})"

    prompt = f"""Eres el asistente del bot de gastos de Jordi y Nani. Responde en español mexicano, breve y directo (máx 2 oraciones). Usa emojis con moderación.

{resumen_ctx or "Sin datos de gastos este mes."}
{ultimo_ctx}

Pregunta: "{texto}"

Si no puedes responder con los datos disponibles, di que no tienes esa información."""

    respuesta = await asyncio.to_thread(groq_completar, prompt, 150)
    if respuesta:
        await update.message.reply_text(respuesta)
        return True
    return False

async def generar_insight_groq(gasto: dict, user_id: int, context) -> None:
    """
    Después de guardar un gasto, verifica si la categoría supera su promedio.
    Se llama en background — no bloquea la confirmación del gasto.
    Solo actúa si el total acumulado en la categoría supera $3,000.
    """
    if not GROQ_API_KEY:
        return

    presupuesto = gasto.get("presupuesto", "")
    mes_actual = gasto.get("mes", "")
    if not presupuesto or not mes_actual:
        return

    try:
        mid = buscar_mes_id(mes_actual)
        if not mid:
            return
        gastos_mes = await asyncio.to_thread(
            query_notion_db, NOTION_DATABASE_ID,
            {"property": "Mes", "relation": {"contains": mid}}
        )
        total_categoria = sum(
            (g.get("properties", {}).get("Monto", {}).get("number", 0) or 0)
            for g in gastos_mes
            if next((k for k, v in PR.items()
                     if v == (g.get("properties", {}).get("Presupuesto", {}).get("relation", [{}])[0].get("id", "")).replace("-", "")),
                    None) == presupuesto
        )

        if total_categoria < 3000:
            return

        prompt = f"""Bot de gastos personales. Acaban de registrar:
- {gasto['concepto']}: ${gasto['monto']:,.2f}
- Categoría {presupuesto}, total acumulado este mes: ${total_categoria:,.2f}

¿Hay algo notable? Responde en 1 línea en español o exactamente "sin_insight" si no hay nada relevante."""

        insight = await asyncio.to_thread(groq_completar, prompt, 60)
        if insight and insight.strip() != "sin_insight" and len(insight) > 5:
            await context.bot.send_message(chat_id=user_id, text=f"💡 {insight}")
    except Exception as e:
        logger.debug(f"Insight omitido: {e}")

# ── NOTION GASTOS ────────────────────────────────────────────────────────────
def guardar_notion(gasto):
    props={
        "Concepto":{"title":[{"text":{"content":gasto["concepto"]}}]},
        "Monto":{"number":gasto["monto"]},
        "Fecha":{"date":{"start":gasto["fecha"]}},
        "Estado de Cuenta":{"rich_text":[{"text":{"content":gasto["tarjeta"]}}]},
        "Pago":{"select":{"name":gasto["tarjeta"]}},
    }
    mid = buscar_mes_id(gasto["mes"])
    if mid:
        props["Mes"] = {"relation":[{"id":mid}]}
    else:
        logger.error(f"Mes {gasto['mes']} sin ID — gasto guardado SIN relacion de mes")
    sid=SC.get(gasto["subcategoria"])
    if sid: props["Subcategoria"]={"relation":[{"id":sid}]}
    pid=PR.get(gasto["presupuesto"])
    if pid: props["Presupuesto"]={"relation":[{"id":pid}]}
    r=notion_request("POST",f"{NOTION_API_BASE}/pages",headers=nh(),
        json={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props},timeout=NOTION_T_DEFAULT)
    if r and r.status_code==200:
        return True, r.json().get("id",""), ""
    return False, "", (r.text if r else "Sin respuesta")

def actualizar_notion(page_id,sub=None,pre=None):
    props={}
    if sub:
        sid=SC.get(sub)
        if sid: props["Subcategoria"]={"relation":[{"id":sid}]}
    if pre:
        pid=PR.get(pre)
        if pid: props["Presupuesto"]={"relation":[{"id":pid}]}
    r=notion_request("PATCH",f"{NOTION_API_BASE}/pages/{page_id}",
        headers=nh(),json={"properties":props},timeout=NOTION_T_DEFAULT)
    return r is not None and r.status_code==200

# ── MENSAJES ─────────────────────────────────────────────────────────────────
def fmt(f):
    return datetime.datetime.strptime(f,"%Y-%m-%d").strftime("%d %b %Y").lower()

def msg_gasto(g, nombre=None, notion_id=None):
    enc = f"🔔 Nuevo gasto de {nombre}" if nombre else "✅ Gasto guardado"
    msg = (
        f"{enc}\n\n"
        f"📌 {g['concepto']}\n"
        f"💵 ${g['monto']:,.2f}\n"
        f"🗓️ {fmt(g['fecha'])}\n"
        f"💳 {g['tarjeta']}\n"
        f"🧾 {g['mes']}\n"
        f"🏷️ {g['subcategoria']}\n"
        f"🗂️ {g['presupuesto']}"
    )
    if notion_id:
        msg += f"\n[🔗 Ver en Notion]({notion_deep_link(notion_id)})"
    return msg

# ── REGISTRAR Y NOTIFICAR ────────────────────────────────────────────────────
async def registrar_y_notificar(update, context, gasto):
    ok, nid, err = guardar_notion(gasto)
    if not ok:
        logger.error(f"Error guardando en Notion: {err}")
        await update.message.reply_text("❌ Error al guardar en Notion. Intenta de nuevo.", reply_markup=ReplyKeyboardRemove())
        return
    gasto_completo = {**gasto, "notion_id": nid}
    uid = update.effective_user.id
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
    guardar_contexto(uid, gasto_completo)
    asyncio.create_task(generar_insight_groq(gasto_completo, uid, context))
    import random
    if random.randint(1,50)==1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()
    await update.message.reply_text(
        msg_gasto(gasto, notion_id=nid),
        reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown"
    )
    notif = USUARIOS_NOTIFICAR.get(uid)
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    if notif:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría", callback_data=f"cor:{nid}:{gasto['concepto']}")]])
        await context.bot.send_message(
            chat_id=notif, text=msg_gasto(gasto, nombre=nombre, notion_id=nid),
            reply_markup=kb, parse_mode="Markdown"
        )

# ── REGISTRAR VIA SHORTCUT (iOS) ─────────────────────────────────────────────
async def registrar_via_shortcut(texto: str, user_id: int):
    import random
    app = get_app()
    if not app:
        return False, "Bot no disponible"
    try:
        gasto = None
        if GROQ_API_KEY and not _parece_gasto_estricto(texto):
            gasto = parsear_mensaje_groq(texto)
        if gasto is None:
            gasto = parsear_mensaje(texto)
    except ValueError as e:
        await app.bot.send_message(chat_id=user_id, text=f"❓ {e}\n\nEjemplo: Oxxo 45")
        return False, str(e)
    except Exception as e:
        await app.bot.send_message(chat_id=user_id, text=f"❌ Error al procesar: {e}")
        return False, str(e)
    ok, nid, err = guardar_notion(gasto)
    if not ok:
        logger.error(f"Error Notion via shortcut: {err}")
        await app.bot.send_message(chat_id=user_id, text="❌ Error al guardar en Notion. Intenta de nuevo.")
        return False, f"Error Notion: {err}"
    gasto_completo = {**gasto, "notion_id": nid}
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, user_id), daemon=True).start()
    guardar_contexto(user_id, gasto_completo)
    if random.randint(1, 50) == 1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()
    msg = msg_gasto(gasto, notion_id=nid)
    if not gasto.get("seguro"):
        msg += "\n\n⚠️ Categoría inferida — usa /corregir si no es correcta."
    await app.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
    notif = USUARIOS_NOTIFICAR.get(user_id)
    nombre = USUARIOS_NOMBRES.get(user_id, "Alguien")
    if notif:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría", callback_data=f"cor:{nid}:{gasto['concepto']}")]])
        await app.bot.send_message(
            chat_id=notif, text=msg_gasto(gasto, nombre=nombre, notion_id=nid),
            reply_markup=kb, parse_mode="Markdown"
        )
    return True, msg

async def _cancelar_conv(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── CONV FOTO ─────────────────────────────────────────────────────────────────
async def handle_foto(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    if not GROQ_API_KEY and not GOOGLE_VISION_API_KEY:
        await update.message.reply_text("❌ No hay servicio de lectura de tickets configurado.")
        return ConversationHandler.END
    msg_espera = await update.message.reply_text("📸 Analizando ticket...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    # Intentar con Llama 4 Scout primero (más preciso, sin regex)
    datos = await asyncio.to_thread(analizar_ticket_groq, bytes(image_bytes))

    # Fallback a Google Vision si Groq no está disponible o falla
    if datos is None:
        texto_ocr = ocr_ticket(bytes(image_bytes))
        if not texto_ocr:
            await msg_espera.edit_text("❌ No pude leer el ticket. Intenta con mejor iluminación o más cerca.")
            return ConversationHandler.END
        datos = parsear_ticket(texto_ocr)

    if not datos or datos.get("monto") is None:
        await msg_espera.edit_text("❌ No encontré el monto en el ticket.")
        return ConversationHandler.END
    fecha   = datos["fecha"]
    tarjeta = calcular_tarjeta(fecha)
    mes     = calcular_mes(fecha, tarjeta)
    sub, pre, seguro = inferir_categoria(datos["concepto"])
    gasto = {
        "concepto": datos["concepto"], "monto": datos["monto"],
        "fecha": fecha.strftime("%Y-%m-%d"), "tarjeta": tarjeta,
        "mes": mes, "subcategoria": sub, "presupuesto": pre, "seguro": seguro,
    }
    context.user_data["gasto_foto"] = gasto
    aviso = "\n⚠️ Categoría inferida." if not seguro else ""
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data="foto_confirmar"),
        InlineKeyboardButton("❌ Cancelar",  callback_data="foto_cancelar"),
    ]])
    await msg_espera.edit_text(
        f"📋 Resumen del ticket\n\n"
        f"📌 {gasto['concepto']}\n💵 ${gasto['monto']:,.2f}\n🗓️ {fmt(gasto['fecha'])}\n"
        f"💳 {gasto['tarjeta']}\n🧾 {gasto['mes']}\n🏷️ {gasto['subcategoria']}\n🗂️ {gasto['presupuesto']}{aviso}",
        reply_markup=kb
    )
    return FOTO_CONFIRMAR

async def callback_foto(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "foto_cancelar":
        context.user_data.clear()
        await query.message.edit_text("❌ Registro cancelado.")
        return ConversationHandler.END
    gasto = context.user_data.pop("gasto_foto", None)
    if not gasto:
        await query.message.edit_text("❌ Error: no se encontró el gasto.")
        return ConversationHandler.END
    ok, nid, err = guardar_notion(gasto)
    if not ok:
        await query.message.edit_text("❌ Error al guardar en Notion.")
        return ConversationHandler.END
    gasto_completo = {**gasto, "notion_id": nid}
    uid = query.from_user.id
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
    await query.message.edit_text(msg_gasto(gasto, notion_id=nid), parse_mode="Markdown")
    notif  = USUARIOS_NOTIFICAR.get(uid)
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    if notif:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría", callback_data=f"cor:{nid}:{gasto['concepto']}")]])
        await context.bot.send_message(
            chat_id=notif, text=msg_gasto(gasto, nombre=nombre, notion_id=nid),
            reply_markup=kb, parse_mode="Markdown"
        )
    return ConversationHandler.END

# ── CONV GASTO ───────────────────────────────────────────────────────────────
async def handle_gasto(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    texto=update.message.text.strip()
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    if len(partes) > 1:
        lineas = []
        gastos_ok = []
        uid = update.effective_user.id
        for parte in partes:
            try:
                gasto = parsear_mensaje(parte)
                ok, nid, err = guardar_notion(gasto)
                if ok:
                    gasto_completo = {**gasto, "notion_id": nid}
                    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
                    lineas.append(f"✅ {gasto['concepto']}  ${gasto['monto']:,.2f}")
                    gastos_ok.append(gasto_completo)
                else:
                    lineas.append(f"❌ {parte.strip()[:20]} (error Notion)")
            except ValueError as e:
                lineas.append(f"❌ {parte.strip()[:20]} ({e})")
        await update.message.reply_text("\n".join(lineas), reply_markup=ReplyKeyboardRemove())
        notif  = USUARIOS_NOTIFICAR.get(uid)
        nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
        if notif and gastos_ok:
            for g in gastos_ok:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría", callback_data=f"cor:{g['notion_id']}:{g['concepto']}")]])
                await context.bot.send_message(
                    chat_id=notif, text=msg_gasto(g, nombre=nombre, notion_id=g["notion_id"]),
                    reply_markup=kb, parse_mode="Markdown"
                )
        return ConversationHandler.END
    # Consulta en lenguaje natural (no es un gasto)
    if not _parece_gasto_estricto(texto) and not _parece_gasto(texto):
        respondido = await responder_consulta_groq(
            texto, update.effective_user.id, update, context
        )
        if respondido:
            return ConversationHandler.END
    try:
        # Intentar con Groq si el mensaje no tiene formato estricto
        gasto = None
        if GROQ_API_KEY and not _parece_gasto_estricto(texto):
            gasto = parsear_mensaje_groq(texto)
        if gasto is None:
            gasto = parsear_mensaje(texto)
        if gasto["monto"]>=MONTO_INUSUAL:
            context.user_data["gasto_pendiente"]=gasto
            await update.message.reply_text(
                f"⚠️ El monto ${gasto['monto']:,.2f} es inusual.\n¿Confirmas '{gasto['concepto']}'?",
                reply_markup=ReplyKeyboardMarkup([["✅ SI","❌ NO"]],one_time_keyboard=True,resize_keyboard=True))
            return CONFIRMAR_MONTO
        if not gasto["seguro"]:
            context.user_data["gasto_pendiente"]=gasto
            await update.message.reply_text(
                f"❓ No reconoci '{gasto['concepto']}'.\n¿En qué categoría va?",
                reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
            return CONFIRMAR_CAT
        await registrar_y_notificar(update,context,gasto)
    except ValueError as e: await update.message.reply_text(f"❓ {e}\n\nEjemplo: Starbucks 150")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def confirmar_monto(update,context):
    gasto=context.user_data.pop("gasto_pendiente",None)
    if "SI" in update.message.text.strip().upper() and gasto: await registrar_y_notificar(update,context,gasto)
    else: await update.message.reply_text("❌ Gasto cancelado.",reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def confirmar_cat(update, context):
    txt = update.message.text.strip()
    if txt == BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    gasto = context.user_data.get("gasto_pendiente")
    if not gasto:
        await update.message.reply_text("Error.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    grp = grupo_key(txt)
    subcats = GRUPOS_CAT.get(grp, [grp])
    context.user_data["grupo_pendiente"] = grp
    if len(subcats) > 1:
        menu = [[s] for s in subcats] + [[BTN_CANCELAR]]
        await update.message.reply_text(
            "🏷️ ¿Qué subcategoría?",
            reply_markup=ReplyKeyboardMarkup(menu, one_time_keyboard=True, resize_keyboard=True)
        )
        return CONFIRMAR_SUBCAT
    gasto = context.user_data.pop("gasto_pendiente")
    gasto["subcategoria"] = subcats[0]
    gasto["presupuesto"] = limpiar_emoji(grp)
    guardar_aprendizaje(gasto["concepto"].lower(), gasto["subcategoria"], gasto["presupuesto"])
    await registrar_y_notificar(update, context, gasto)
    return ConversationHandler.END

async def confirmar_subcat(update, context):
    txt = update.message.text.strip()
    if txt == BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    gasto = context.user_data.pop("gasto_pendiente", None)
    grp   = context.user_data.pop("grupo_pendiente", txt)
    if not gasto:
        await update.message.reply_text("Error.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    gasto["subcategoria"] = txt
    gasto["presupuesto"]  = limpiar_emoji(grp)
    guardar_aprendizaje(gasto["concepto"].lower(), txt, limpiar_emoji(grp))
    await registrar_y_notificar(update, context, gasto)
    context.user_data.clear()
    return ConversationHandler.END

# ── CONV CORREGIR ────────────────────────────────────────────────────────────
_NUM_EMOJI = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]

def _lista_corregir(ultimos):
    txt = "✏️ Elige el gasto a corregir:\n\n"
    for i, g in enumerate(ultimos):
        num = _NUM_EMOJI[i] if i < len(_NUM_EMOJI) else f"{i+1}."
        fecha_c = " ".join(fmt(g["fecha"]).split()[:2]) if g.get("fecha") else ""
        txt += f"{num}  {g['concepto']}  —  ${g['monto']:,.2f}\n"
        txt += f"     🏷️ {g['subcategoria']}  ·  {g['presupuesto']}"
        if fecha_c:
            txt += f"  ·  🗓️ {fecha_c}"
        txt += "\n\n"
    return txt

async def cmd_corregir(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    uid = update.effective_user.id
    ultimos = cargar_historial_notion(uid)
    if not ultimos:
        await update.message.reply_text("No hay gastos recientes para corregir."); return ConversationHandler.END
    context.user_data["historial_corregir"]=ultimos
    await update.message.reply_text(_lista_corregir(ultimos),reply_markup=ReplyKeyboardMarkup(menu_elegir(ultimos),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_ELEGIR

async def corregir_elegir(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    try:
        idx=int(txt)-1
        if idx < 0: raise IndexError
        gasto=context.user_data["historial_corregir"][idx]
        context.user_data["gasto_corregir"]=gasto
    except (ValueError, IndexError, KeyError):
        await update.message.reply_text(
            "❓ Escribe el número del gasto (1-5) o usa ❌ Cancelar.",
            reply_markup=ReplyKeyboardMarkup(menu_elegir(context.user_data.get("historial_corregir",[])),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_ELEGIR
    await update.message.reply_text(
        f"📌 {gasto['concepto']}\n🏷️ {gasto['subcategoria']}  •  {gasto['presupuesto']}\n\n¿Qué quieres corregir?",
        reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_QUE

async def corregir_que(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    if txt==BTN_REGRESAR:
        ultimos=context.user_data.get("historial_corregir",[])
        await update.message.reply_text(_lista_corregir(ultimos),reply_markup=ReplyKeyboardMarkup(menu_elegir(ultimos),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_ELEGIR
    context.user_data["que_corregir"]=txt
    if "Monto" in txt or "💵" in txt:
        await update.message.reply_text(
            "💵 ¿Cuál es el monto correcto?",
            reply_markup=ReplyKeyboardMarkup([[BTN_CANCELAR]], one_time_keyboard=True, resize_keyboard=True)
        )
        return CORREGIR_MONTO
    if "Presupuesto" in txt and "Subcategoría" not in txt and "Ambas" not in txt:
        await update.message.reply_text("💰 Elige el nuevo presupuesto:",reply_markup=ReplyKeyboardMarkup(menu_presupuesto(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_PRESU
    await update.message.reply_text("🏷️ Paso 1: Elige la categoría principal:",reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_CAT_GRP

async def corregir_cat_grp(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    if txt==BTN_REGRESAR:
        gasto=context.user_data.get("gasto_corregir",{})
        await update.message.reply_text(f"📌 {gasto.get('concepto','')}\n\n¿Qué quieres corregir?",
            reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_QUE
    grp=grupo_key(txt); context.user_data["grupo_elegido"]=grp
    subcats=GRUPOS_CAT.get(grp,[grp])
    if len(subcats)==1:
        context.user_data["nueva_sub"]=subcats[0]
        que=context.user_data.get("que_corregir","")
        if "Ambas" in que:
            await update.message.reply_text(f"Subcategoria: {subcats[0]}\n\n💰 Elige el presupuesto:",
                reply_markup=ReplyKeyboardMarkup(menu_presupuesto(),one_time_keyboard=True,resize_keyboard=True))
            return CORREGIR_PRESU
        return await aplicar_correccion(update,context,sub=subcats[0])
    menu=[[s] for s in subcats]+[[BTN_REGRESAR,BTN_CANCELAR]]
    await update.message.reply_text("🏷️ Elige la subcategoria:",reply_markup=ReplyKeyboardMarkup(menu,one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_SUBCAT

async def corregir_subcat(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    if txt==BTN_REGRESAR:
        await update.message.reply_text("🏷️ Paso 1: Elige la categoría principal:",
            reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_CAT_GRP
    context.user_data["nueva_sub"]=txt
    que=context.user_data.get("que_corregir","")
    if "Ambas" in que:
        await update.message.reply_text("💰 Elige el presupuesto:",
            reply_markup=ReplyKeyboardMarkup(menu_presupuesto(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_PRESU
    return await aplicar_correccion(update,context,sub=txt)

async def corregir_presu(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    if txt==BTN_REGRESAR:
        que=context.user_data.get("que_corregir","")
        if "Ambas" in que:
            grp=context.user_data.get("grupo_elegido","")
            subcats=GRUPOS_CAT.get(grp,[grp])
            if len(subcats)>1:
                menu=[[s] for s in subcats]+[[BTN_REGRESAR,BTN_CANCELAR]]
                await update.message.reply_text("🏷️ Elige la subcategoria:",
                    reply_markup=ReplyKeyboardMarkup(menu,one_time_keyboard=True,resize_keyboard=True))
                return CORREGIR_SUBCAT
            await update.message.reply_text("🏷️ Paso 1: Elige la categoría principal:",
                reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
            return CORREGIR_CAT_GRP
        gasto=context.user_data.get("gasto_corregir",{})
        await update.message.reply_text(f"📌 {gasto.get('concepto','')}\n\n¿Qué quieres corregir?",
            reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_QUE
    return await aplicar_correccion(update,context,pre=presu_limpio(txt))

async def corregir_monto(update, context):
    txt = update.message.text.strip()
    if txt == BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    try:
        monto = float(txt.replace("$", "").replace(",", ""))
        if monto <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❓ Escribe un monto válido (ej: 150).")
        return CORREGIR_MONTO
    gasto = context.user_data.get("gasto_corregir")
    if not gasto:
        await update.message.reply_text("Error.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{gasto['notion_id']}",
        headers=nh(), json={"properties": {"Monto": {"number": monto}}}, timeout=NOTION_T_DEFAULT)
    if r and r.status_code == 200:
        nid  = gasto.get("notion_id", "")
        link = f"\n[🔗 Ver en Notion]({notion_deep_link(nid)})" if nid else ""
        await update.message.reply_text(
            f"✅ Monto corregido\n\n📌 {gasto['concepto']}\n💵 ${monto:,.2f}{link}",
            reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown"
        )
        notif  = USUARIOS_NOTIFICAR.get(update.effective_user.id)
        nombre = USUARIOS_NOMBRES.get(update.effective_user.id, "Alguien")
        if notif:
            await context.bot.send_message(
                chat_id=notif,
                text=f"✏️ {nombre} corrigió un gasto\n\n📌 {gasto['concepto']}\n💵 ${monto:,.2f}{link}",
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text("❌ Error al actualizar Notion.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def aplicar_correccion(update, context, sub=None, pre=None):
    gasto     = context.user_data.get("gasto_corregir")
    nueva_sub = sub or context.user_data.get("nueva_sub")
    nuevo_pre = pre
    if not gasto:
        await update.message.reply_text("Error.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    ok = actualizar_notion(gasto["notion_id"], sub=nueva_sub, pre=nuevo_pre)
    if ok:
        guardar_aprendizaje(
            gasto["concepto"].lower(),
            nueva_sub or gasto.get("subcategoria",""),
            nuevo_pre or gasto.get("presupuesto","")
        )
        resumen = f"📌 {gasto['concepto']}\n"
        if nueva_sub: resumen += f"🏷️ {nueva_sub}\n"
        if nuevo_pre: resumen += f"🗂️ {nuevo_pre}\n"
        nid  = gasto.get("notion_id","")
        link = f"\n[🔗 Ver en Notion]({notion_deep_link(nid)})" if nid else ""
        await update.message.reply_text(
            f"✅ Corregido\n\n{resumen}{link}",
            reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown"
        )
        uid    = update.effective_user.id
        nombre = USUARIOS_NOMBRES.get(uid,"Alguien")
        notif  = USUARIOS_NOTIFICAR.get(uid)
        if notif:
            await context.bot.send_message(
                chat_id=notif, text=f"✏️ {nombre} corrigió un gasto\n\n{resumen}{link}",
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text("❌ Error al actualizar Notion.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def callback_corregir(update,context):
    query=update.callback_query; await query.answer()
    if query.from_user.id not in USUARIOS_AUTORIZADOS: return
    partes=query.data.split(":",2)
    nid=partes[1]; concepto=partes[2] if len(partes)>2 else "Gasto"
    context.user_data["gasto_corregir"]={"notion_id":nid,"concepto":concepto}
    await query.message.reply_text(
        f"📌 {concepto}\n\n¿Qué quieres corregir?",
        reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_QUE

async def cmd_prueba(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    await update.message.reply_text(
        "🧪 Modo prueba activado. Escribe el gasto normalmente.\n"
        "No se registrará nada en Notion. El modo prueba dura solo un mensaje."
    )
    return PRUEBA_GASTO

async def handle_prueba(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    texto=update.message.text.strip()
    try:
        tokens=texto.strip().split()
        hoy=datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        fecha,tokens2=parsear_fecha(tokens); texp,tokens2=parsear_tarjeta(tokens2); monto,tokens2=parsear_monto(tokens2)
        concepto=" ".join(tokens2).strip()
        if not concepto: raise ValueError("No encontré el concepto")
        if monto is None: raise ValueError("No encontré el monto")
        tarjeta=calcular_tarjeta(fecha,texp); mes=calcular_mes(fecha,tarjeta)
        sub,pre,seguro,origen_emoji,origen_texto=inferir_categoria_con_origen(concepto)
        fecha_fmt=datetime.datetime.strptime(fecha.strftime("%Y-%m-%d"),"%Y-%m-%d").strftime("%d %b %Y").lower()
        await update.message.reply_text(
            f"🧪 Resultado de prueba\n\n"
            f"📌 {concepto.title()}\n💵 ${monto:,.2f}\n🗓️ {fecha_fmt}\n"
            f"💳 {tarjeta}\n🧾 {mes}\n🏷️ {sub}\n🗂️ {pre}\n\n"
            f"🔍 Origen: {origen_emoji} {origen_texto}\n\n"
            f"Nada fue registrado en Notion."
        )
    except ValueError as e:
        await update.message.reply_text(f"❓ {e}\n\nEjemplo: Starbucks 150\n\nYa saliste del modo prueba.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}\n\nYa saliste del modo prueba.")
    return ConversationHandler.END

async def cancelar(update,context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def start(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return
    nombre = USUARIOS_NOMBRES.get(update.effective_user.id, "")
    await update.message.reply_text(
        f"Hola {nombre} 👋\n\n"
        "💸 *Cómo anotar un gasto*\n"
        "`Concepto  Monto  [Tarjeta]  [Fecha]`\n\n"
        "Starbucks 150\n"
        "Gasolina 500 BBVA05\n"
        "Walmart 350 ayer\n"
        "Oxxo Gas 400 15-may\n\n"
        "📸 También puedes mandar una foto del ticket\n\n"
        "💳 *Tarjetas*\n"
        "BBVA05 · BBVA12 · HEYB25 · BMEX04 · EFVO\n\n"
        "📋 *Comandos*\n"
        "/resumen — mes activo _(también: /resumen MAY26)_\n"
        "/estadisticas — este mes vs el anterior\n"
        "/corregir — cambiar categoría o monto\n"
        "/eliminar — borrar el último gasto\n"
        "/prueba — simular sin registrar",
        parse_mode="Markdown"
    )

async def cmd_estadisticas(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return
    mes_act = mes_activo_str()
    mes_nombre = mes_act[:3]
    anio = int("20" + mes_act[3:])
    mes_num = next((k for k, v in MESES_ESP.items() if v == mes_nombre), 1)
    if mes_num == 1:
        mes_ant_num, anio_ant = 12, anio - 1
    else:
        mes_ant_num, anio_ant = mes_num - 1, anio
    mes_ant = f"{MESES_ESP[mes_ant_num]}{str(anio_ant)[-2:]}"

    await update.message.reply_text(f"⏳ Comparando {mes_ant} vs {mes_act}...")

    def get_totales(mes):
        mid = buscar_mes_id(mes)
        if not mid:
            return {}
        gastos = query_notion_db(NOTION_DATABASE_ID,
                                 {"property": "Mes", "relation": {"contains": mid}})
        totales = {}
        for g in gastos:
            props = g.get("properties", {})
            monto = props.get("Monto", {}).get("number", 0) or 0
            rel_pre = props.get("Presupuesto", {}).get("relation", [])
            if rel_pre:
                pr_id = rel_pre[0].get("id", "").replace("-", "")
                nombre = next((k for k, v in PR.items() if v == pr_id), None)
                if nombre:
                    totales[nombre] = totales.get(nombre, 0) + monto
        return totales

    totales_ant = await asyncio.to_thread(get_totales, mes_ant)
    totales_act = await asyncio.to_thread(get_totales, mes_act)

    if not totales_ant and not totales_act:
        await update.message.reply_text("❌ No se pudieron obtener los datos.")
        return

    total_ant = sum(totales_ant.values())
    total_act = sum(totales_act.values())
    categorias = sorted(set(totales_ant) | set(totales_act),
                        key=lambda c: totales_act.get(c, 0), reverse=True)

    max_nom = max((len(c) for c in categorias), default=8)
    tabla = []
    for cat in categorias:
        a, b = totales_ant.get(cat, 0), totales_act.get(cat, 0)
        diff = b - a
        emoji = PR_EMOJI.get(cat, "📦")
        e_str = emoji + " " if emoji in EMOJI_ESTRECHO else emoji
        arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "=")
        monto_s = f"${b:,.0f}".rjust(7)
        diff_s  = f"{abs(diff):>6,.0f}"
        tabla.append(f"{e_str} {cat.ljust(max_nom)}  {monto_s}  {arrow}{diff_s}")

    diff_total = total_act - total_ant
    flecha = "▲" if diff_total > 0 else "▼"

    # Línea vacía al inicio del code block para que el botón </>
    # de Telegram no tape la primera fila de datos
    msg = (
        f"📊 *{mes_ant} → {mes_act}*\n\n"
        f"```\n\n{chr(10).join(tabla)}\n```\n\n"
        f"💰 *{mes_act}*   ${total_act:,.0f}\n"
        f"💰 *{mes_ant}*   ${total_ant:,.0f}\n\n"
        f"{flecha} *Diferencia*   ${abs(diff_total):,.0f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ── /BUSCAR y /TOP ────────────────────────────────────────────────────────────
def _gasto_props(page):
    p = page.get("properties", {})
    titulo = p.get("Concepto", {}).get("title", [])
    concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
    monto = p.get("Monto", {}).get("number", 0) or 0
    fecha = (p.get("Fecha", {}).get("date", {}) or {}).get("start", "")
    return concepto, monto, fecha

def _fecha_corta(fecha):
    return " ".join(fmt(fecha).split()[:2]) if fecha else ""

async def cmd_buscar(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return
    q = " ".join(context.args).strip()
    if not q:
        await update.message.reply_text("🔍 Uso: /buscar <texto>\nEjemplo: /buscar uber")
        return
    await update.message.reply_text(f"🔍 Buscando \"{q}\"...")

    def _buscar():
        r = notion_request("POST", f"{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query",
            headers=nh(),
            json={
                "filter": {"property": "Concepto", "title": {"contains": q}},
                "sorts": [{"property": "Fecha", "direction": "descending"}],
                "page_size": 12,
            }, timeout=NOTION_T_LONG)
        return r.json().get("results", []) if r and r.status_code == 200 else []

    resultados = await asyncio.to_thread(_buscar)
    if not resultados:
        await update.message.reply_text(f"📭 No encontré gastos con \"{q}\".")
        return
    lineas = [f"🔍 *{q}* — {len(resultados)} resultado(s)\n"]
    suma = 0
    for page in resultados:
        concepto, monto, fecha = _gasto_props(page)
        suma += monto
        lineas.append(f"📌 {concepto}   ${monto:,.0f}   ·   {_fecha_corta(fecha)}")
    lineas.append(f"\n💰 *Suma mostrada*   ${suma:,.0f}")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")

async def cmd_top(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return
    mes = context.args[0].upper() if context.args else mes_activo_str()
    mid = buscar_mes_id(mes)
    if not mid:
        await update.message.reply_text(f"❌ No encontré el mes {mes} en Notion.")
        return
    await update.message.reply_text(f"⏳ Top gastos de {mes}...")

    def _top():
        gastos = query_notion_db(NOTION_DATABASE_ID, {"property": "Mes", "relation": {"contains": mid}})
        items = [_gasto_props(g) for g in gastos]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:5]

    top = await asyncio.to_thread(_top)
    if not top:
        await update.message.reply_text(f"📭 No hay gastos en {mes}.")
        return
    lineas = [f"🏆 *Top 5 — {mes}*\n"]
    for i, (concepto, monto, fecha) in enumerate(top):
        num = _NUM_EMOJI[i] if i < len(_NUM_EMOJI) else f"{i+1}."
        lineas.append(f"{num}  {concepto}   ${monto:,.0f}   ·   {_fecha_corta(fecha)}")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")

async def cmd_eliminar(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    uid = update.effective_user.id
    historial = cargar_historial_notion(uid)
    if not historial:
        await update.message.reply_text("No hay gastos recientes para eliminar.")
        return ConversationHandler.END
    ultimo = historial[0]
    context.user_data["gasto_eliminar"] = ultimo
    await update.message.reply_text(
        f"🗑️ ¿Eliminar este gasto?\n\n"
        f"📌 {ultimo['concepto']}\n"
        f"💵 ${ultimo['monto']:,.2f}\n"
        f"🗓️ {fmt(ultimo['fecha'])}\n"
        f"🏷️ {ultimo['subcategoria']}  •  {ultimo['presupuesto']}",
        reply_markup=ReplyKeyboardMarkup([["✅ Sí, eliminar", "❌ No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return ELIMINAR_CONFIRM

async def eliminar_confirmar(update, context):
    txt = update.message.text.strip()
    if "SI" not in txt.upper() and "SÍ" not in txt.upper():
        return await _cancelar_conv(update, context)
    gasto = context.user_data.pop("gasto_eliminar", None)
    if not gasto or not gasto.get("notion_id"):
        await update.message.reply_text("❌ No se encontró el gasto en Notion.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{gasto['notion_id']}",
        headers=nh(), json={"archived": True}, timeout=NOTION_T_DEFAULT)
    if r and r.status_code == 200:
        await update.message.reply_text(
            f"🗑️ Eliminado\n\n📌 {gasto['concepto']}  ${gasto['monto']:,.2f}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text("❌ Error al eliminar en Notion.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ── WEBHOOK HANDLER ───────────────────────────────────────────────────────────
_ptb_app = None

def get_app():
    global _ptb_app
    return _ptb_app

class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","text/plain")
        self.send_header("Content-Length","2"); self.end_headers()
        self.wfile.write(b"OK"); self.wfile.flush()

    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Type","text/plain"); self.end_headers()

    def do_POST(self):
        import asyncio
        path = self.path.split("?")[0]

        if path == "/log":
            logger.info(f"/log recibido desde {self.client_address}")
            try:
                length  = int(self.headers.get("Content-Length", 0))
                body    = self.rfile.read(length)
                data    = json.loads(body.decode("utf-8"))
                SC_SECRET = os.environ.get("SHORTCUT_SECRET", "")
                if SC_SECRET and data.get("secret") != SC_SECRET:
                    self.send_response(403); self.send_header("Content-Type","application/json"); self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"unauthorized"}'); return
                texto   = data.get("text", "").strip()
                user_id = int(data.get("user_id", 8663298433))
                logger.info(f"/log texto='{texto[:60]}' user_id={user_id}")
                if not texto:
                    self.send_response(400); self.send_header("Content-Type","application/json"); self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"texto vacio"}'); return
                app  = get_app()
                loop = getattr(getattr(app, "update_processor", None), "_loop", None)
                if loop:
                    future  = asyncio.run_coroutine_threadsafe(registrar_via_shortcut(texto, user_id), loop)
                    ok, msg = future.result(timeout=NOTION_T_LONG)
                else:
                    logger.error("/log: loop no disponible"); ok, msg = False, "Loop no disponible"
                resp = json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False).encode()
                self.send_response(200); self.send_header("Content-Type","application/json")
                self.send_header("Content-Length", str(len(resp))); self.end_headers(); self.wfile.write(resp)
            except Exception as e:
                logger.error(f"Error en /log: {e}")
                resp = json.dumps({"ok": False, "error": str(e)}).encode()
                self.send_response(500); self.send_header("Content-Type","application/json")
                self.send_header("Content-Length", str(len(resp))); self.end_headers(); self.wfile.write(resp)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            if WEBHOOK_SECRET:
                token_header = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if token_header != WEBHOOK_SECRET:
                    self.send_response(403); self.end_headers(); return
            update_data = json.loads(body.decode("utf-8"))
            app = get_app()
            if app:
                update = Update.de_json(update_data, app.bot)
                asyncio.run_coroutine_threadsafe(
                    app.process_update(update),
                    app.update_processor._loop if hasattr(app.update_processor, '_loop') else asyncio.get_event_loop()
                )
            self.send_response(200); self.end_headers()
        except Exception as e:
            logger.error(f"Error en webhook POST: {e}")
            self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass

# ── MAIN ──────────────────────────────────────────────────────────────────────
import asyncio

async def setup_webhook(app):
    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
    params = {"url": webhook_url, "drop_pending_updates": True}
    if WEBHOOK_SECRET:
        params["secret_token"] = WEBHOOK_SECRET
    await app.bot.set_webhook(**params)
    info = await app.bot.get_webhook_info()
    logger.info(f"Webhook configurado: {info.url}")

def main():
    global _ptb_app
    precargar_meses()
    app = Application.builder().token(TELEGRAM_TOKEN).updater(None).job_queue(None).build()
    _ptb_app = app

    conv_prueba = ConversationHandler(
        entry_points=[CommandHandler("prueba", cmd_prueba)],
        states={PRUEBA_GASTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prueba)]},
        fallbacks=[CommandHandler("cancelar", cancelar)], allow_reentry=True,
    )
    conv_foto = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, handle_foto)],
        states={FOTO_CONFIRMAR: [CallbackQueryHandler(callback_foto, pattern="^foto_")]},
        fallbacks=[CommandHandler("cancelar", cancelar)], allow_reentry=True,
    )
    conv_gasto = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gasto)],
        states={
            CONFIRMAR_MONTO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_monto)],
            CONFIRMAR_CAT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_cat)],
            CONFIRMAR_SUBCAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_subcat)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar), CommandHandler("start", start)],
        allow_reentry=True,
    )
    conv_corregir = ConversationHandler(
        entry_points=[CommandHandler("corregir", cmd_corregir), CallbackQueryHandler(callback_corregir, pattern="^cor:")],
        states={
            CORREGIR_ELEGIR:  [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_elegir)],
            CORREGIR_QUE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_que)],
            CORREGIR_CAT_GRP: [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_cat_grp)],
            CORREGIR_SUBCAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_subcat)],
            CORREGIR_PRESU:   [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_presu)],
            CORREGIR_MONTO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_monto)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)], allow_reentry=True,
    )
    conv_eliminar = ConversationHandler(
        entry_points=[CommandHandler("eliminar", cmd_eliminar)],
        states={ELIMINAR_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, eliminar_confirmar)]},
        fallbacks=[CommandHandler("cancelar", cancelar)], allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", cmd_resumen))
    app.add_handler(CommandHandler("estadisticas", cmd_estadisticas))
    app.add_handler(CommandHandler("buscar", cmd_buscar))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(conv_prueba)
    app.add_handler(conv_foto)
    app.add_handler(conv_corregir)
    app.add_handler(conv_eliminar)
    app.add_handler(conv_gasto)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(setup_webhook(app))
    loop.run_until_complete(app.start())
    app.update_processor._loop = loop

    port = int(os.environ.get("PORT", 10000))
    logger.info(f"HTTP en {port}")
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    threading.Thread(target=loop.run_forever, daemon=True).start()
    logger.info("Bot corriendo v_final17...")
    server.serve_forever()

if __name__ == "__main__":
    main()
