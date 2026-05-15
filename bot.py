import os, re, datetime, requests, threading, unicodedata, json, logging, time
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
WEBHOOK_SECRET        = os.environ.get("WEBHOOK_SECRET", "")
RENDER_EXTERNAL_URL   = os.environ.get("RENDER_EXTERNAL_URL", "")

USUARIOS_AUTORIZADOS = {8663298433, 8093171397}
USUARIOS_NOMBRES     = {8663298433: "Jordi", 8093171397: "Nane"}
USUARIOS_NOTIFICAR   = {8663298433: 8093171397, 8093171397: 8663298433}

MONTO_INUSUAL    = 5000
CONFIRMAR_MONTO  = 1
CONFIRMAR_CAT    = 2
CORREGIR_ELEGIR  = 10
CORREGIR_QUE     = 11
CORREGIR_CAT_GRP = 12
CORREGIR_SUBCAT  = 13
CORREGIR_PRESU   = 14
PRUEBA_GASTO     = 20

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

# ── NOTION BALANCE (meses dinamicos) ─────────────────────────────────────────
NOTION_BALANCE_ID = os.environ.get("NOTION_BALANCE_ID", "")
_meses_cache: dict = {}

def buscar_mes_id(mes: str):
    if mes in _meses_cache:
        return _meses_cache[mes]
    if not NOTION_BALANCE_ID:
        logger.warning("NOTION_BALANCE_ID no configurado")
        return None
    try:
        r = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_BALANCE_ID}/query",
            headers=nh(),
            json={"filter": {"property": "Name", "title": {"equals": mes}}},
            timeout=5,
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                mid = results[0]["id"]
                _meses_cache[mes] = mid
                return mid
        logger.warning(f"Mes {mes} no encontrado en Notion")
    except Exception as e:
        logger.error(f"Error buscando mes {mes}: {e}")
    return None

# ── CONCEPTOS UNIVOCOS — nunca guardar en Aprendizaje ────────────────────────
# Son conceptos que SIEMPRE mapean a la misma categoria sin excepcion posible
CONCEPTOS_UNIVOCOS = {
    "netflix","spotify","disney","hbo","apple tv","paramount","crunchyroll",
    "max","prime video","izzi","telmex","adobe","icloud","capcut","claude",
    "figma","canva","microsoft","chatgpt","at&t","att","cfe","mapfre",
    "seguro auto","qualitas","walmart","soriana","bodega aurrera","oxxo gas","oxxogas",
    "sam's","chedraui","zarapes",
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
        ["✏️ Ambas"],
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
    (["restaurante","taqueria","tacos","pizza","sushi","pollo bronco","dq ","dairy queen","carl's","mcdonald","burger","kfc","subway","domino","clip mx*rest","payclip*rest","la choco","mamma farina","dolce natura","los elotis","punto sur","barbacos","barbacoa","velma","calena","bistro","brüm","brum","meridiao","uber eats","rappi"],"Restaurantes","Restaurantes"),
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
    (["uber ","didi ","cabify"],"Gasolina","Automovil"),
]

MESES_ESP   = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}
MESES_TEXTO = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,
               "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,
               "septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}

# ── HELPERS ──────────────────────────────────────────────────────────────────
def normalizar(t):
    t=t.lower().strip(); t=unicodedata.normalize("NFD",t)
    return "".join(c for c in t if unicodedata.category(c)!="Mn")

def similitud(a,b): return SequenceMatcher(None,normalizar(a),normalizar(b)).ratio()
def nh(): return {"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"}

# ── REINTENTOS ───────────────────────────────────────────────────────────────
def notion_request(method, url, **kwargs):
    """Wrapper con 3 reintentos automaticos (espera 2s entre cada uno)."""
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

# ── APRENDIZAJE ──────────────────────────────────────────────────────────────
def buscar_aprendizaje(concepto):
    r = notion_request("POST",
        f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",
        headers=nh(),
        json={"filter":{"property":"Concepto","title":{"equals":concepto.lower()}}},
        timeout=5)
    if r and r.status_code == 200:
        res = r.json().get("results", [])
        if res:
            p = res[0]["properties"]
            s = p.get("Subcategoria",{}).get("rich_text",[])
            b = p.get("Presupuesto",{}).get("rich_text",[])
            if s and b: return s[0]["text"]["content"], b[0]["text"]["content"]
    return None, None

def guardar_aprendizaje(concepto, sub, pre):
    """Guarda o actualiza aprendizaje. Omite conceptos univocos y actualiza fecha."""
    # No guardar si es un concepto que siempre tiene la misma categoria
    if es_concepto_univoco(concepto):
        logger.info(f"Concepto univoco '{concepto}' — omitiendo aprendizaje")
        return

    hoy = datetime.date.today().isoformat()
    r = notion_request("POST",
        f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",
        headers=nh(),
        json={"filter":{"property":"Concepto","title":{"equals":concepto.lower()}}},
        timeout=5)
    if r and r.status_code == 200:
        res = r.json().get("results", [])
        if res:
            pid = res[0]["id"]
            u = res[0]["properties"].get("Usos",{}).get("number",0) or 0
            notion_request("PATCH",
                f"https://api.notion.com/v1/pages/{pid}",
                headers=nh(),
                json={"properties":{
                    "Subcategoria":{"rich_text":[{"text":{"content":sub}}]},
                    "Presupuesto":{"rich_text":[{"text":{"content":pre}}]},
                    "Usos":{"number":u+1},
                    "Fecha":{"date":{"start":hoy}},
                }},
                timeout=5)
            return
    notion_request("POST",
        "https://api.notion.com/v1/pages",
        headers=nh(),
        json={"parent":{"database_id":NOTION_APRENDIZAJE_ID},"properties":{
            "Concepto":{"title":[{"text":{"content":concepto.lower()}}]},
            "Subcategoria":{"rich_text":[{"text":{"content":sub}}]},
            "Presupuesto":{"rich_text":[{"text":{"content":pre}}]},
            "Usos":{"number":1},
            "Fecha":{"date":{"start":hoy}},
        }},
        timeout=5)

def limpiar_aprendizaje():
    """Limpia entradas obsoletas de la base de aprendizaje.
    Regla 1: Usos=1 y sin actividad en 90 dias -> borrar
    Regla 2: Si hay mas de 150 entradas, borrar las de menor uso hasta llegar a 100"""
    try:
        hoy = datetime.date.today()
        limite_90 = (hoy - datetime.timedelta(days=90)).isoformat()
        # Traer todas las entradas
        r = notion_request("POST",
            f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",
            headers=nh(), json={"page_size":200}, timeout=10)
        if not r or r.status_code != 200: return
        entradas = r.json().get("results", [])
        borradas = 0
        # Regla 1: Usos=1 y fecha antigua
        for e in entradas:
            p = e["properties"]
            usos = p.get("Usos",{}).get("number",0) or 0
            fecha_raw = p.get("Fecha",{}).get("date")
            fecha_str = fecha_raw["start"] if fecha_raw else None
            if usos == 1 and fecha_str and fecha_str < limite_90:
                notion_request("DELETE", f"https://api.notion.com/v1/pages/{e['id']}",
                    headers=nh(), timeout=5)
                borradas += 1
        # Regla 2: limite de 150 entradas
        if len(entradas) - borradas > 150:
            sobrantes = sorted(entradas, key=lambda e: e["properties"].get("Usos",{}).get("number",0) or 0)
            por_borrar = (len(entradas) - borradas) - 100
            for e in sobrantes[:por_borrar]:
                notion_request("DELETE", f"https://api.notion.com/v1/pages/{e['id']}",
                    headers=nh(), timeout=5)
                borradas += 1
        if borradas: logger.info(f"Limpieza aprendizaje: {borradas} entradas eliminadas")
    except Exception as ex:
        logger.error(f"Error en limpiar_aprendizaje: {ex}")

# ── HISTORIAL PERSISTENTE ────────────────────────────────────────────────────
MAX_HISTORIAL = 5

def guardar_historial_notion(gasto, usuario_id):
    """Guarda el gasto en la base Historial Bot (mantiene solo los ultimos 5)."""
    try:
        # Guardar nueva entrada
        notion_request("POST",
            "https://api.notion.com/v1/pages",
            headers=nh(),
            json={"parent":{"database_id":NOTION_HISTORIAL_ID},"properties":{
                "Concepto":  {"title":[{"text":{"content":gasto["concepto"]}}]},
                "Monto":     {"number":gasto["monto"]},
                "Fecha":     {"date":{"start":gasto["fecha"]}},
                "Tarjeta":   {"rich_text":[{"text":{"content":gasto["tarjeta"]}}]},
                "Mes":       {"rich_text":[{"text":{"content":gasto["mes"]}}]},
                "Subcategoria":{"rich_text":[{"text":{"content":gasto["subcategoria"]}}]},
                "Presupuesto": {"rich_text":[{"text":{"content":gasto["presupuesto"]}}]},
                "NotionID":  {"rich_text":[{"text":{"content":gasto.get("notion_id","")}}]},
                "UsuarioID": {"number":usuario_id},
            }},
            timeout=5)
        # Limpiar entradas viejas — mantener solo las ultimas MAX_HISTORIAL por usuario
        r = notion_request("POST",
            f"https://api.notion.com/v1/databases/{NOTION_HISTORIAL_ID}/query",
            headers=nh(),
            json={
                "filter":{"property":"UsuarioID","number":{"equals":usuario_id}},
                "sorts":[{"timestamp":"created_time","direction":"descending"}],
                "page_size": 20,
            },
            timeout=5)
        if r and r.status_code == 200:
            entradas = r.json().get("results",[])
            for vieja in entradas[MAX_HISTORIAL:]:
                notion_request("PATCH",
                    f"https://api.notion.com/v1/pages/{vieja['id']}",
                    headers=nh(),
                    json={"archived": True},
                    timeout=5)
    except Exception as ex:
        logger.error(f"Error guardando historial: {ex}")

def cargar_historial_notion(usuario_id):
    """Carga los ultimos MAX_HISTORIAL gastos del usuario desde Notion."""
    try:
        r = notion_request("POST",
            f"https://api.notion.com/v1/databases/{NOTION_HISTORIAL_ID}/query",
            headers=nh(),
            json={
                "filter":{"property":"UsuarioID","number":{"equals":usuario_id}},
                "sorts":[{"timestamp":"created_time","direction":"descending"}],
                "page_size": MAX_HISTORIAL,
            },
            timeout=5)
        if r and r.status_code == 200:
            resultado = []
            for e in r.json().get("results",[]):
                p = e["properties"]
                def txt(campo): return (p.get(campo,{}).get("rich_text",[{}])[0].get("text",{}).get("content","") if p.get(campo,{}).get("rich_text") else "")
                resultado.append({
                    "concepto":    (p.get("Concepto",{}).get("title",[{}])[0].get("text",{}).get("content","") if p.get("Concepto",{}).get("title") else ""),
                    "monto":       p.get("Monto",{}).get("number",0) or 0,
                    "fecha":       (p.get("Fecha",{}).get("date",{}) or {}).get("start",""),
                    "tarjeta":     txt("Tarjeta"),
                    "mes":         txt("Mes"),
                    "subcategoria":txt("Subcategoria"),
                    "presupuesto": txt("Presupuesto"),
                    "notion_id":   txt("NotionID"),
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
    except: pass
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
    """Como inferir_categoria pero devuelve (sub, pre, seguro, origen_emoji, origen_texto)."""
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
    else: mp=m  # EFVO
    while mp>12: mp-=12; y+=1
    return f"{MESES_ESP[mp]}{str(y)[-2:]}"

# ── PARSEO ───────────────────────────────────────────────────────────────────
def parsear_fecha(tokens):
    import zoneinfo; hoy=datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    for i,t in enumerate(tokens):
        tl=t.lower()
        if tl=="ayer": return hoy-datetime.timedelta(days=1),tokens[:i]+tokens[i+1:]
        if tl=="hoy": return hoy,tokens[:i]+tokens[i+1:]
        m=re.match(r'^(\d{1,2})[-/](\d{1,2})$',t)
        if m:
            try: return datetime.date(hoy.year,int(m.group(2)),int(m.group(1))),tokens[:i]+tokens[i+1:]
            except: pass
        m=re.match(r'^(\d{1,2})[-/]([a-z]+)$',tl)
        if m and m.group(2) in MESES_TEXTO:
            try: return datetime.date(hoy.year,MESES_TEXTO[m.group(2)],int(m.group(1))),tokens[:i]+tokens[i+1:]
            except: pass
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
        except: pass
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

# ── NOTION GASTOS ────────────────────────────────────────────────────────────
def guardar_notion(gasto):
    props={
        "Concepto":{"title":[{"text":{"content":gasto["concepto"]}}]},
        "Monto":{"number":gasto["monto"]},
        "Fecha":{"date":{"start":gasto["fecha"]}},
        "Estado de Cuenta":{"rich_text":[{"text":{"content":gasto["tarjeta"]}}]},
        "Pago":{"select":{"name":gasto["tarjeta"]}},
    }
    mid=buscar_mes_id(gasto["mes"])
    if mid: props["Mes"]={"relation":[{"id":mid}]}
    sid=SC.get(gasto["subcategoria"])
    if sid: props["Subcategoria"]={"relation":[{"id":sid}]}
    pid=PR.get(gasto["presupuesto"])
    if pid: props["Presupuesto"]={"relation":[{"id":pid}]}
    r=notion_request("POST","https://api.notion.com/v1/pages",headers=nh(),
        json={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props},timeout=8)
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
    r=notion_request("PATCH",f"https://api.notion.com/v1/pages/{page_id}",
        headers=nh(),json={"properties":props},timeout=8)
    return r is not None and r.status_code==200

# ── MENSAJES ─────────────────────────────────────────────────────────────────
def fmt(f):
    from datetime import datetime as dt
    return dt.strptime(f,"%Y-%m-%d").strftime("%d %b %Y").lower()

def msg_gasto(g,nombre=None):
    enc=f"🔔 Nuevo gasto de {nombre}" if nombre else "✅ Gasto guardado"
    return f"{enc}\n\n📌 {g['concepto']}\n💵 ${g['monto']:,.2f}\n🗓️ {fmt(g['fecha'])}\n💳 {g['tarjeta']}  •  Mes: {g['mes']}\n🏷️ {g['subcategoria']}  •  {g['presupuesto']}"

# ── REGISTRAR Y NOTIFICAR ────────────────────────────────────────────────────
async def registrar_y_notificar(update,context,gasto):
    ok,nid,err=guardar_notion(gasto)
    if not ok:
        logger.error(f"Error guardando en Notion: {err}")
        await update.message.reply_text("❌ Error al guardar en Notion. Intenta de nuevo.",reply_markup=ReplyKeyboardRemove())
        return
    gasto_completo = {**gasto,"notion_id":nid}
    uid = update.effective_user.id
    # Historial persistente en Notion (no en RAM)
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
    # Limpieza periodica de aprendizaje (1 de cada 50 gastos aprox, no bloquea)
    import random
    if random.randint(1,50)==1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()
    await update.message.reply_text(msg_gasto(gasto),reply_markup=ReplyKeyboardRemove())
    notif=USUARIOS_NOTIFICAR.get(uid); nombre=USUARIOS_NOMBRES.get(uid,"Alguien")
    if notif:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría",callback_data=f"cor:{nid}:{gasto['concepto']}")]])
        await context.bot.send_message(chat_id=notif,text=msg_gasto(gasto,nombre=nombre),reply_markup=kb)

# ── REGISTRAR VIA SHORTCUT (iOS) ─────────────────────────────────────────────
async def registrar_via_shortcut(texto: str, user_id: int):
    """Procesa y registra un gasto enviado desde el Shortcut de iOS sin update/context."""
    import random
    app = get_app()
    if not app:
        return False, "Bot no disponible"
    try:
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
    if random.randint(1, 50) == 1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()

    msg = msg_gasto(gasto)
    if not gasto.get("seguro"):
        msg += "\n\n⚠️ Categoría inferida — usa /corregir si no es correcta."
    await app.bot.send_message(chat_id=user_id, text=msg)

    notif = USUARIOS_NOTIFICAR.get(user_id)
    nombre = USUARIOS_NOMBRES.get(user_id, "Alguien")
    if notif:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría", callback_data=f"cor:{nid}:{gasto['concepto']}")]])
        await app.bot.send_message(chat_id=notif, text=msg_gasto(gasto, nombre=nombre), reply_markup=kb)

    return True, msg

# ── CONV GASTO ───────────────────────────────────────────────────────────────
async def handle_gasto(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    texto=update.message.text.strip()
    try:
        gasto=parsear_mensaje(texto)
        if gasto["monto"]>=MONTO_INUSUAL:
            context.user_data["gasto_p"]=gasto
            await update.message.reply_text(
                f"⚠️ El monto ${gasto['monto']:,.2f} es inusual.\n¿Confirmas '{gasto['concepto']}'?",
                reply_markup=ReplyKeyboardMarkup([["✅ SI","❌ NO"]],one_time_keyboard=True,resize_keyboard=True))
            return CONFIRMAR_MONTO
        if not gasto["seguro"]:
            context.user_data["gasto_p"]=gasto
            await update.message.reply_text(
                f"❓ No reconoci '{gasto['concepto']}'.\n¿En qué categoría va?",
                reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
            return CONFIRMAR_CAT
        await registrar_y_notificar(update,context,gasto)
    except ValueError as e: await update.message.reply_text(f"❓ {e}\n\nEjemplo: Starbucks 150")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def confirmar_monto(update,context):
    gasto=context.user_data.pop("gasto_p",None)
    if "SI" in update.message.text.strip().upper() and gasto: await registrar_y_notificar(update,context,gasto)
    else: await update.message.reply_text("❌ Gasto cancelado.",reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def confirmar_cat(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    gasto=context.user_data.pop("gasto_p",None)
    if not gasto:
        await update.message.reply_text("Error.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    grp=grupo_key(txt); subcats=GRUPOS_CAT.get(grp,[grp])
    gasto["subcategoria"]=subcats[0]; gasto["presupuesto"]=limpiar_emoji(grp)
    guardar_aprendizaje(gasto["concepto"].lower(),gasto["subcategoria"],gasto["presupuesto"])
    await registrar_y_notificar(update,context,gasto)
    return ConversationHandler.END

# ── CONV CORREGIR ────────────────────────────────────────────────────────────
async def cmd_corregir(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    uid = update.effective_user.id
    ultimos = cargar_historial_notion(uid)
    if not ultimos:
        await update.message.reply_text("No hay gastos recientes para corregir."); return ConversationHandler.END
    texto="✏️ Elige el gasto a corregir:\n\n"
    for i,g in enumerate(ultimos): texto+=f"{i+1}. {g['concepto']}  ${g['monto']:,.2f}\n    🏷️ {g['subcategoria']}  •  {g['presupuesto']}\n\n"
    context.user_data["historial_corregir"]=ultimos
    await update.message.reply_text(texto,reply_markup=ReplyKeyboardMarkup(menu_elegir(ultimos),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_ELEGIR

async def corregir_elegir(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    try:
        idx=int(txt)-1
        gasto=context.user_data["historial_corregir"][idx]
        context.user_data["gasto_corregir"]=gasto
    except:
        await update.message.reply_text("Opcion no valida.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    await update.message.reply_text(
        f"📌 {gasto['concepto']}\n🏷️ {gasto['subcategoria']}  •  {gasto['presupuesto']}\n\n¿Qué quieres corregir?",
        reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_QUE

async def corregir_que(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    if txt==BTN_REGRESAR:
        ultimos=context.user_data.get("historial_corregir",[])
        texto="✏️ Elige el gasto a corregir:\n\n"
        for i,g in enumerate(ultimos): texto+=f"{i+1}. {g['concepto']}  ${g['monto']:,.2f}\n    🏷️ {g['subcategoria']}  •  {g['presupuesto']}\n\n"
        await update.message.reply_text(texto,reply_markup=ReplyKeyboardMarkup(menu_elegir(ultimos),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_ELEGIR
    context.user_data["que_corregir"]=txt
    if "Presupuesto" in txt and "Subcategoría" not in txt and "Ambas" not in txt:
        await update.message.reply_text("💰 Elige el nuevo presupuesto:",reply_markup=ReplyKeyboardMarkup(menu_presupuesto(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_PRESU
    await update.message.reply_text("🏷️ Paso 1: Elige la categoría principal:",reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_CAT_GRP

async def corregir_cat_grp(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
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
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
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
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
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

async def aplicar_correccion(update,context,sub=None,pre=None):
    gasto=context.user_data.get("gasto_corregir")
    nueva_sub=sub or context.user_data.get("nueva_sub")
    nuevo_pre=pre
    if not gasto:
        await update.message.reply_text("Error.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    ok=actualizar_notion(gasto["notion_id"],sub=nueva_sub,pre=nuevo_pre)
    if ok:
        guardar_aprendizaje(gasto["concepto"].lower(),nueva_sub or gasto.get("subcategoria",""),nuevo_pre or gasto.get("presupuesto",""))
        resumen=f"📌 {gasto['concepto']}\n"
        if nueva_sub: resumen+=f"🏷️ Subcategoria: {nueva_sub}\n"
        if nuevo_pre: resumen+=f"💰 Presupuesto: {nuevo_pre}\n"
        await update.message.reply_text(f"✅ Corregido y aprendido\n\n{resumen}",reply_markup=ReplyKeyboardRemove())
        uid=update.effective_user.id
        nombre=USUARIOS_NOMBRES.get(uid,"Alguien")
        notif=USUARIOS_NOTIFICAR.get(uid)
        if notif:
            await context.bot.send_message(chat_id=notif,text=f"✏️ {nombre} corrigió un gasto\n\n{resumen}")
    else:
        await update.message.reply_text("❌ Error al actualizar Notion.",reply_markup=ReplyKeyboardRemove())
    context.user_data.clear(); return ConversationHandler.END

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
        # Parsear sin guardar nada
        tokens=texto.strip().split()
        import zoneinfo; hoy=datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        fecha,tokens2=parsear_fecha(tokens); texp,tokens2=parsear_tarjeta(tokens2); monto,tokens2=parsear_monto(tokens2)
        concepto=" ".join(tokens2).strip()
        if not concepto: raise ValueError("No encontré el concepto")
        if monto is None: raise ValueError("No encontré el monto")
        tarjeta=calcular_tarjeta(fecha,texp); mes=calcular_mes(fecha,tarjeta)
        sub,pre,seguro,origen_emoji,origen_texto=inferir_categoria_con_origen(concepto)
        from datetime import datetime as dt
        fecha_fmt=dt.strptime(fecha.strftime("%Y-%m-%d"),"%Y-%m-%d").strftime("%d %b %Y").lower()
        respuesta=(
            f"🧪 Resultado de prueba\n\n"
            f"📌 {concepto.title()}\n"
            f"💵 ${monto:,.2f}\n"
            f"🗓️ {fecha_fmt}\n"
            f"💳 {tarjeta}  •  Mes: {mes}\n"
            f"🏷️ {sub}  •  {pre}\n\n"
            f"🔍 Origen: {origen_emoji} {origen_texto}\n\n"
            f"Nada fue registrado en Notion. Ya saliste del modo prueba."
        )
        await update.message.reply_text(respuesta)
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
    await update.message.reply_text(
        "👋 Hola! Soy tu bot de gastos.\n\n"
        "Escríbeme así:\n"
        "Concepto Monto\n\n"
        "Ejemplos:\n"
        "Starbucks 150\n"
        "Gasolina 500 BBVA05\n"
        "Walmart 350 ayer\n"
        "Netflix 299 HEYB25\n"
        "Oxxo Gas 400 15-may\n\n"
        "Tarjetas disponibles:\n"
        "BBVA05  BBVA12  HEYB25  BMEX04  EFVO\n\n"
        "Comandos:\n"
        "/corregir — corregir subcategoria o presupuesto de un gasto reciente\n"
        "/prueba — simular un gasto sin registrar nada en Notion\n"
        "/cancelar — cancelar cualquier accion en curso"
    )

# ── WEBHOOK HANDLER ───────────────────────────────────────────────────────────
_ptb_app = None

def get_app():
    global _ptb_app
    return _ptb_app

class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")
        self.wfile.flush()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def do_POST(self):
        import asyncio
        path = self.path.split("?")[0]

        # ── /log  →  iOS Shortcut ─────────────────────────────────────────
        if path == "/log":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length)
                data   = json.loads(body.decode("utf-8"))

                SC_SECRET = os.environ.get("SHORTCUT_SECRET", "")
                if SC_SECRET and data.get("secret") != SC_SECRET:
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"unauthorized"}')
                    return

                texto   = data.get("text", "").strip()
                user_id = int(data.get("user_id", 8663298433))

                if not texto:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"texto vacio"}')
                    return

                app  = get_app()
                loop = getattr(getattr(app, "update_processor", None), "_loop", None)
                if loop:
                    future   = asyncio.run_coroutine_threadsafe(
                        registrar_via_shortcut(texto, user_id), loop)
                    ok, msg  = future.result(timeout=15)
                else:
                    ok, msg  = False, "Loop no disponible"

                resp = json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                logger.error(f"Error en /log: {e}")
                resp = json.dumps({"ok": False, "error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        # ── /webhook  →  Telegram ─────────────────────────────────────────
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            if WEBHOOK_SECRET:
                token_header = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if token_header != WEBHOOK_SECRET:
                    self.send_response(403)
                    self.end_headers()
                    return
            update_data = json.loads(body.decode("utf-8"))
            app = get_app()
            if app:
                update = Update.de_json(update_data, app.bot)
                asyncio.run_coroutine_threadsafe(
                    app.process_update(update),
                    app.update_processor._loop if hasattr(app.update_processor, '_loop') else asyncio.get_event_loop()
                )
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            logger.error(f"Error en webhook POST: {e}")
            self.send_response(200)
            self.end_headers()

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
    app = Application.builder().token(TELEGRAM_TOKEN).updater(None).job_queue(None).build()
    _ptb_app = app

    conv_prueba = ConversationHandler(
        entry_points=[CommandHandler("prueba", cmd_prueba)],
        states={
            PRUEBA_GASTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prueba)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    conv_gasto = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gasto)],
        states={
            CONFIRMAR_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_monto)],
            CONFIRMAR_CAT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_cat)],
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
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_prueba)
    app.add_handler(conv_corregir)
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
    logger.info("Bot corriendo v_final5...")
    server.serve_forever()

if __name__ == "__main__":
    main()
