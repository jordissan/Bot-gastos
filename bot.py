from __future__ import annotations  # anotaciones lazy — permite correr tests en Python 3.9 local
import os, re, datetime, requests, threading, unicodedata, json, logging, time, base64, zoneinfo, asyncio
from difflib import SequenceMatcher
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN        = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN          = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID    = os.environ["NOTION_DATABASE_ID"]
NOTION_APRENDIZAJE_ID = "3ba6f37c717948a1a6aeac3b384ff33c"
NOTION_HISTORIAL_ID   = "35f7eb0cbb9280ae8f02f69b4f242298"
NOTION_METAS_ID       = "cf7906bcccfd4690b7ef8c1e996a8e17"
NOTION_ALIAS_ID       = "9000583a97204e6db41994ec96bf5a71"
GOOGLE_MAPS_API_KEY   = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", "")
WEBHOOK_SECRET        = os.environ.get("WEBHOOK_SECRET", "")
RENDER_EXTERNAL_URL   = os.environ.get("RENDER_EXTERNAL_URL", "")
NOTION_BALANCE_ID     = os.environ.get("NOTION_BALANCE_ID", "")
GROQ_API_KEY          = os.environ.get("GROQ_API_KEY", "")
RESEND_API_KEY        = os.environ.get("RESEND_API_KEY", "")
REPORTE_EMAIL         = os.environ.get("REPORTE_EMAIL", "jor.jorwww@gmail.com")
SHORTCUT_SECRET       = os.environ.get("SHORTCUT_SECRET", "")
# Memoria persistente: filas especiales en NOTION_HISTORIAL_ID con UsuarioID=0
# Concepto = MEM_{uid} · JSON en campo NotionID · filas ya existen en Historial Bot

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

def groq_transcribir(audio_bytes: bytes, filename: str = "audio.ogg"):
    """Transcribe audio a texto con Whisper (Groq). Retorna el texto o None si falla."""
    client = get_groq()
    if not client:
        return None
    try:
        result = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3-turbo",
            language="es",
        )
        return (result.text or "").strip()
    except Exception as e:
        logger.warning(f"Groq transcripción error: {e}")
        return None

def _extraer_json(raw):
    """Extrae un objeto JSON de una respuesta del LLM, tolerando fences y prosa alrededor."""
    if not raw:
        return None
    import re as _re
    s = _re.sub(r'^```(?:json)?\s*', '', raw.strip())
    s = _re.sub(r'\s*```$', '', s.strip())
    try:
        return json.loads(s)
    except Exception:
        pass
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(s[i:j + 1])
        except Exception:
            return None
    return None

# ── MEMORIA CONVERSACIONAL PERSISTENTE ────────────────────────────────────────
# RAM (instancia activa) + Notion (persiste entre reinicios de Render).
# Estructura por uid:
#   turns        → últimos 8 turnos [{r:"u"|"b", t:"texto"}]
#   last_results → hasta 10 gastos del último query [{concepto,monto,notion_id,fecha}]
#   last_query   → parámetros del último query
#   last_gasto   → último gasto registrado {concepto,monto,notion_id,fecha}
#   loaded       → True si ya se intentó cargar desde Notion esta sesión
_memoria_ram: dict = {}
_ultimo_gasto_usuario = {}  # Gasto COMPLETO para edición contextual (mantiene todos los campos)
_staged_edits: dict = {}   # uid → {"campos": {...}, "base": gasto_dict} — edición pendiente de confirmar

def _mem_init(uid: int) -> dict:
    if uid not in _memoria_ram:
        _memoria_ram[uid] = {
            "turns": [], "last_results": [], "last_query": {},
            "last_gasto": {}, "loaded": False,
        }
    return _memoria_ram[uid]

# ── I/O Notion (síncronos; llamar con asyncio.to_thread) ─────────────────────

def _leer_memoria_notion(uid: int) -> dict:
    """Lee memoria desde la fila MEM_{uid} en Historial Bot (UsuarioID=0)."""
    try:
        rows = query_notion_db(NOTION_HISTORIAL_ID, {"and": [
            {"property": "UsuarioID", "number": {"equals": 0}},
            {"property": "Concepto",  "title":  {"equals": f"MEM_{uid}"}},
        ]})
        if not rows:
            return {}
        rt = rows[0]["properties"].get("NotionID", {}).get("rich_text", [])
        raw = "".join(t.get("plain_text", "") for t in rt)
        return json.loads(raw) if raw else {}
    except Exception as e:
        logger.warning(f"[Mem] leer uid={uid}: {e}")
        return {}

def _escribir_memoria_notion(uid: int, data: dict):
    """Escribe memoria en la fila MEM_{uid} en Historial Bot (campo NotionID)."""
    try:
        raw = json.dumps(data, ensure_ascii=False)
        if len(raw) > 1900:
            tr = {**data, "turns": data.get("turns", [])[-4:]}
            raw = json.dumps(tr, ensure_ascii=False)[:1900]
        props = {
            "NotionID": {"rich_text": [{"type": "text", "text": {"content": raw}}]},
        }
        rows = query_notion_db(NOTION_HISTORIAL_ID, {"and": [
            {"property": "UsuarioID", "number": {"equals": 0}},
            {"property": "Concepto",  "title":  {"equals": f"MEM_{uid}"}},
        ]})
        if rows:
            notion_request("PATCH", f"{NOTION_API_BASE}/pages/{rows[0]['id']}",
                headers=nh(), json={"properties": props}, timeout=NOTION_T_DEFAULT)
        else:
            # Fallback: crear la fila si no existe
            nombre = USUARIOS_NOMBRES.get(uid, str(uid))
            notion_request("POST", f"{NOTION_API_BASE}/pages", headers=nh(), json={
                "parent": {"database_id": NOTION_HISTORIAL_ID},
                "properties": {
                    "Concepto":  {"title":     [{"type": "text", "text": {"content": f"MEM_{uid}"}}]},
                    "UsuarioID": {"number":    0},
                    "Tarjeta":   {"rich_text": [{"type": "text", "text": {"content": "MEMORIA_BOT"}}]},
                    "Mes":       {"rich_text": [{"type": "text", "text": {"content": nombre}}]},
                    **props,
                },
            }, timeout=NOTION_T_DEFAULT)
    except Exception as e:
        logger.warning(f"[Mem] escribir uid={uid}: {e}")

# ── API pública ───────────────────────────────────────────────────────────────

async def mem_cargar(uid: int):
    """Cold-start: carga Notion → RAM. No-op si ya se cargó esta sesión."""
    m = _mem_init(uid)
    if m["loaded"]:
        return
    try:
        data = await asyncio.to_thread(_leer_memoria_notion, uid)
        if data:
            m["turns"]        = data.get("turns", [])[-8:]
            m["last_results"] = data.get("last_results", [])
            m["last_query"]   = data.get("last_query", {})
            m["last_gasto"]   = data.get("last_gasto", {})
            # TTL: resultados con más de 2 horas = stale, se descartan
            updated = data.get("updated_at", "")
            if updated:
                try:
                    delta = (datetime.datetime.utcnow() -
                             datetime.datetime.fromisoformat(updated.replace("Z", ""))).total_seconds()
                    if delta > 7200:
                        m["last_results"] = []
                        m["last_query"]   = {}
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[Mem] cargar uid={uid}: {e}")
    finally:
        m["loaded"] = True

async def mem_guardar(uid: int):
    """Persiste RAM → Notion en background (no bloquea al usuario)."""
    m = _mem_init(uid)
    data = {
        "turns":        m["turns"][-8:],
        "last_results": m["last_results"][:10],
        "last_query":   m["last_query"],
        "last_gasto":   m["last_gasto"],
        "updated_at":   datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    await asyncio.to_thread(_escribir_memoria_notion, uid, data)

def mem_add_turn(uid: int, role: str, text: str):
    m = _mem_init(uid)
    m["turns"].append({"r": role[0], "t": text[:200]})
    if len(m["turns"]) > 8:
        m["turns"] = m["turns"][-8:]

def mem_get_turns(uid: int) -> list:
    """Historial en formato [{role, content}] listo para el prompt de Groq."""
    return [{"role": "user" if t["r"] == "u" else "assistant", "content": t["t"]}
            for t in _mem_init(uid)["turns"]]

def mem_set_results(uid: int, results: list, query: dict = None):
    """Guarda gastos del último query para referencias como 'dame el link', 'el más caro'."""
    m = _mem_init(uid)
    m["last_results"] = [
        {"concepto": r.get("concepto", ""), "monto": r.get("monto", 0),
         "notion_id": r.get("notion_id", ""), "fecha": str(r.get("fecha", ""))}
        for r in results[:10] if r.get("notion_id")
    ]
    if query:
        m["last_query"] = query

def mem_get_results(uid: int) -> list:
    return _mem_init(uid)["last_results"]

def mem_set_gasto(uid: int, gasto: dict):
    """Guarda el último gasto registrado (simplificado, para links y eliminación)."""
    m = _mem_init(uid)
    m["last_gasto"] = {
        "concepto":  gasto.get("concepto", ""),
        "monto":     gasto.get("monto", 0),
        "notion_id": gasto.get("notion_id", ""),
        "fecha":     str(gasto.get("fecha", "")),
    }

def mem_get_gasto(uid: int) -> dict:
    return _mem_init(uid)["last_gasto"]

# ── Aliases de compatibilidad (el código existente no cambia) ─────────────────

def guardar_contexto(user_id: int, gasto: dict):
    _ultimo_gasto_usuario[user_id] = gasto.copy()  # completo, para edición
    mem_set_gasto(user_id, gasto)                  # simplificado, para refs

def obtener_contexto(user_id: int):
    return _ultimo_gasto_usuario.get(user_id)

def agregar_historial(uid: int, role: str, content: str):
    mem_add_turn(uid, role, content)

def obtener_historial(uid: int) -> list:
    return mem_get_turns(uid)

def limpiar_historial(uid: int):
    if uid in _memoria_ram:
        _memoria_ram[uid]["turns"] = []

USUARIOS_AUTORIZADOS = {8663298433, 8093171397}
USUARIOS_NOMBRES     = {8663298433: "Jordi", 8093171397: "Nani"}
USUARIOS_NOTIFICAR   = {8663298433: 8093171397, 8093171397: 8663298433}

MONTO_INUSUAL    = 5000
CONFIRMAR_MONTO  = 1
CONFIRMAR_CAT    = 2
CONFIRMAR_SUBCAT = 3
CORREGIR_ELEGIR  = 10
CORREGIR_PANEL   = 11   # panel inline multi-campo (híbrido botones + texto)
PRUEBA_GASTO     = 20
FOTO_CONFIRMAR   = 30
ELIMINAR_CONFIRM = 50
PROPUESTA_META   = 60   # estado para ajustar la meta de apertura de ciclo

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
    "Vacaciones":"545753674d4e4d0ca0fd8be7d33db21e",
    "Impuestos":"224cdb40f1f749c7b5d6e165ad31110d","Entretenimiento":"3547eb0cbb92815d8248db75a759646b",
    "Generosidad":"f4cac9f4b95e4508942ad02ae69ddffe","Iglesia":"89b897bd6fa24b8d897adf380491130e",
    "Personal":"829161723b0b49bf8787663a89c7248d","Departamento":"1af955c917f54a2da39e9bbb8e4032ff",
    "Otros":"1ea7eb0cbb9280cbbe43c1bd54396691","Educación":"3677eb0cbb9281c4b82cc803cb114d65",
    "Emergencias":"3677eb0cbb9281598e2fe19be3db3d74",
    "Deudas":"91ab43856d1e4ae69f21f4203eeb3c54",  # alias del grupo "🏦 Deudas" → misma página que "Deuda"
}

PR_EMOJI = {
    "Despensa":"🛒","Diversión":"🎉","Servicios":"🧾","Automovil":"🚗",
    "Restaurantes":"🍽️","Salud":"💊","Deuda":"🏦","MSI":"💳",
    "Renta":"🏠","Ezra":"👶","Vacaciones":"🏖️",
    "Impuestos":"📊","Entretenimiento":"🎭","Generosidad":"🤝","Iglesia":"⛪",
    "Personal":"👤","Departamento":"🏡","Otros":"📦",
    "Educación":"📚","Emergencias":"🚨","Deudas":"🏦",
}

# Subcategoría → Presupuesto. Respaldo cuando el gasto NO tiene relación de Presupuesto
# (el usuario borra la columna Presupuesto cada mes; Subcategoria permanece).
SUBCAT_PRESUPUESTO = {
    "Super":"Despensa","Abarrotes":"Despensa","Carniceria":"Despensa","Mercado":"Despensa","Comida":"Despensa",
    "Restaurantes":"Restaurantes",
    "Gasolina":"Automovil","Estacionamento":"Automovil","Mantenimiento":"Automovil","VW POLO":"Automovil","Seguro Auto":"Automovil",
    "Servicios":"Servicios","Streaming":"Servicios","Internet":"Servicios","Telefonia Celular":"Servicios","Luz":"Servicios","Agua":"Servicios",
    "Renta":"Renta","Muebles":"Departamento","Decoracion":"Departamento",
    "Treat":"Diversión","Salidas":"Diversión","Cine":"Diversión","Conciertos":"Diversión","Tiempo de calidad":"Diversión",
    "Ropa":"Personal","Calzado":"Personal","Gimnasio":"Personal","Corte de pelo":"Personal","Gasto personal":"Personal",
    "Doctor":"Salud","Medicina":"Salud",
    "Cuidado personal":"Personal",
    "Libros":"Educación","Cursos":"Educación",
    "Emergencias":"Emergencias","Ezra":"Ezra",
    "Regalos":"Generosidad","Ofrenda":"Generosidad","Diezmo":"Generosidad",
    "MSI":"MSI","Deudas":"Deuda","EFI":"Deuda","DBMEX":"Deuda","PDHB25":"Deuda","PRP":"Deuda",
    "Impuestos":"Impuestos","Vacaciones":"Vacaciones","Otros":"Otros",
}

# Mapas inversos id_relacion → nombre (para leer un gasto existente desde Notion).
# setdefault conserva el primer nombre cuando varios comparten id (alias como Deuda/Deudas).
SC_INV, PR_INV = {}, {}
for _k, _v in SC.items(): SC_INV.setdefault(_v, _k)
for _k, _v in PR.items(): PR_INV.setdefault(_v, _k)

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
def _dias_en_ciclo() -> int:
    """Días transcurridos del ciclo de facturación en curso (ancla el día 5 = día 1 del ciclo)."""
    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    if hoy.day >= 5:
        return hoy.day - 4
    import calendar
    prev = hoy.replace(day=1) - datetime.timedelta(days=1)
    dias_prev = calendar.monthrange(prev.year, prev.month)[1]
    return (dias_prev - 4) + hoy.day

def calcular_proyeccion(total_actual, meses_anteriores):
    """(proyeccion, delta_pct) proyectando el cierre del ciclo, o None si faltan datos (<2 meses)."""
    historicos = [t for t in meses_anteriores if t and t > 0]
    if len(historicos) < 2:
        return None
    promedio = sum(historicos) / len(historicos)
    dias = max(1, _dias_en_ciclo())
    proyeccion = total_actual / dias * 30
    delta_pct = round((proyeccion - promedio) / promedio * 100) if promedio else 0
    return proyeccion, delta_pct

def generar_narrativa_resumen(mes, totales_dict, total, proyeccion):
    """2-3 líneas de insight del mes redactadas por Groq. None si falla o no hay API."""
    if not GROQ_API_KEY:
        return None
    try:
        cats = ", ".join(f"{k} ${v:,.0f}" for k, v in
                         sorted(totales_dict.items(), key=lambda x: x[1], reverse=True))
        ctx_proy = f"\nProyección de cierre: {proyeccion}" if proyeccion else ""
        prompt = (
            f"Eres el asistente financiero de Jordi y Nani. Mes {mes}. "
            f"Gasto total ${total:,.0f}. Desglose por categoría: {cats}.{ctx_proy}\n\n"
            "Escribe 2-3 líneas en español mexicano, tono directo, SIN saludos ni preámbulo, "
            "con los insights más relevantes (qué categoría pesa más, si algo destaca, si el ritmo "
            "es alto o normal). No repitas el total tal cual; aporta interpretación. Sin markdown."
        )
        return (groq_completar(prompt, max_tokens=80) or "").strip() or None
    except Exception as e:
        logger.warning(f"narrativa resumen error: {e}")
        return None

async def cmd_resumen(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return

    args = context.args
    mes = args[0].upper() if args else mes_activo_str()

    mid = await asyncio.to_thread(buscar_mes_id, mes)
    if not mid:
        await update.message.reply_text(f"❌ No encontré el mes {mes} en Notion.")
        return

    await update.message.reply_text(f"⏳ Calculando resumen de {mes}…")

    gastos = await asyncio.to_thread(query_notion_db, NOTION_DATABASE_ID,
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

    # Metas del ciclo (Feature 3)
    uid_resumen = update.effective_user.id
    metas_ciclo = await asyncio.to_thread(cargar_metas_ciclo, uid_resumen, mes)
    for meta in metas_ciclo:
        presupuesto = meta.get("presupuesto", "")
        limite      = float(meta.get("limite") or 0)
        if not presupuesto or not limite:
            continue
        if presupuesto == "TOTAL":
            usado = total_general
        else:
            usado = totales.get(presupuesto, 0)
        pct   = min((usado / limite) * 100, 999)
        barras = min(int(pct / 10), 10)
        barra  = "█" * barras + "░" * (10 - barras)
        label  = "Total ciclo" if presupuesto == "TOTAL" else presupuesto
        msg   += f"\n🎯 Meta *{label}*: ${usado:,.0f} / ${limite:,.0f} [{barra}] {pct:.0f}%"

    # Proyección de cierre (solo para el mes activo en curso) — Tarea 3
    proy_txt = None
    if mes == mes_activo_str():
        totales_ciclo = _totales_por_ciclo()
        prev = _meses_recientes(4)[1:]   # los 3 ciclos anteriores al activo
        meses_ant = [totales_ciclo.get(m, 0) for m in prev]
        proy = calcular_proyeccion(total_general, meses_ant)
        if proy:
            p, d = proy
            signo = "+" if d >= 0 else ""
            proy_txt = f"~${p:,.0f} al cierre ({signo}{d}% vs promedio)"
            msg += f"\n📈 Proyección: {proy_txt}"

    # Narrativa del mes generada por Groq — Tarea 6
    narrativa = await asyncio.to_thread(generar_narrativa_resumen, mes, dict(ordenados), total_general, proy_txt)
    if narrativa:
        msg += f"\n\n{_esc_md(narrativa)}"

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

REGLAS_CONCEPTO = [
    # ── DESPENSA: super / carniceria ──
    (["walmart","soriana","costco","bodega aurrera","bae ","chedraui","sam's","sams club","heb ","h-e-b","la comer","fresko","city market","calimax","comercial mexicana","superama","s-mart","smart & final"],"Super","Despensa"),
    (["calii"],"Super","Despensa"),
    (["carniceria","carnes especiales","barrangueno","pescaderia","altamez"],"Carniceria","Despensa"),
    # ── RESTAURANTES (antes que abarrotes y treat; "didi food" antes que "didi") ──
    (["zarapes","merpago*zarapes"],"Restaurantes","Despensa"),
    (["restaurante","taqueria","tacos","pizza","sushi","ramen","pollo bronco","dq ","dairy queen","carl's","mcdonald","burger","kfc","subway","domino","clip mx*rest","payclip*rest","la choco","mamma farina","dolce natura","los elotis","punto sur","barbacos","barbacoa","velma","calena","bistro","meridiao","uber eats","rappi","didi food","vips","sanborns","toks","wings","italianni","chili's","chilis","applebee","ihop","sonora grill","fogon","fogoncito","birria","mariscos","sirloin","la mansion","el porton","fonda","cantina","wok ","ostioneria","cevicheria","parrilla","asador","pf chang","casa de tono"],"Restaurantes","Restaurantes"),
    # ── TREAT / café / postres ──
    (["starbucks","cafe ","coffee","brüm","brum","helado","nieve","nieves","paleta","panaderia","pasteleria","cielito querido","el pendulo","italian coffee","punta del cielo","krispy kreme","dunkin","la michoacana","santa clara","haagen","cinnabon","churreria","churros","donas","cheesecake","cupcake","frappe"],"Treat","Diversión"),
    # ── AUTOMOVIL (gasolina antes que "oxxo" de abarrotes) ──
    (["oxxo gas","oxxogas","oxxo gaspaseos","gasolina","bp ","shell ","petro","combustible","pemex","mobil ","g500","arco ","repsol"],"Gasolina","Automovil"),
    (["mapfre","seguro auto","qualitas"],"Seguro Auto","Automovil"),
    (["autolavado","refaccion","mecanico","llantas","verificacion","afinacion","taller "],"Mantenimiento","Automovil"),
    (["parco","conekta*parco","estacionamiento"],"Estacionamento","Automovil"),
    (["uber","didi","cabify"],"Gasolina","Automovil"),
    # ── ABARROTES (después de gasolina por "oxxo gas") ──
    (["oxxo","naranjitas","rancherita","super rancherita","abarrotes","minisuper","seven","barreto","merpago*abarrotes"],"Abarrotes","Despensa"),
    # ── SERVICIOS ──
    (["netflix","spotify","disney","hbo","apple tv","paramount","crunchyroll","max ","prime video","youtube premium","tidal","deezer","mubi","vix","claro video"],"Streaming","Servicios"),
    (["izzi","telmex","megacable","totalplay","total play","axtel"],"Internet","Servicios"),
    (["telcel","movistar","at&t","att ","bait","unefon"],"Telefonia Celular","Servicios"),
    (["cfe"],"Luz","Servicios"),
    (["jumapa","simapag","sapal","siapa","capama","comapa","interapas"],"Agua","Servicios"),
    (["adobe","icloud","capcut","claude","figma","canva","microsoft","chatgpt","openai","notion","dropbox","github","midjourney","perplexity","grammarly","godaddy","namecheap","vercel","hostinger","google"],"Servicios","Servicios"),
    # ── SALUD ──
    (["farmacia guadalajara","farmacia benavides","farmacias del ahorro","farmacia similares","farmacia","dr simi","doctor simi","salud digna","laboratorio","chopo","analisis clinicos"],"Medicina","Salud"),
    (["doctor","hospital","clinica","medico","consulta","dentista","ortodoncia","oftalmologo","optica","lentes","ginecologo","consultorio"],"Doctor","Salud"),
    # ── EZRA (antes de cualquier regla genérica de salud que use "pediatra") ──
    (["gerber","nutrileche","pedialyte","pediatra","pediatria","vacuna","pañal","pañales","formula bebe","leche bebe"],"Ezra","Ezra"),
    # ── PERSONAL: ropa / calzado / gimnasio / corte ──
    (["zara","h&m","bershka","pull&bear","pull and bear","shein","nike","adidas","puma","old navy","gap ","levis","american eagle","forever 21","hollister","calvin klein","suburbia","uniqlo","stradivarius","oysho","sfera","aeropostale"],"Ropa","Personal"),
    (["flexi","andrea","price shoes","dportenis","innovasport","vans","converse","dr martens"],"Calzado","Personal"),
    (["smart fit","smartfit","sports world","sport city","anytime","gimnasio","gym "],"Gimnasio","Personal"),
    (["barberia","barber","peluqueria","estetica","salon ","corte de pelo"],"Corte de pelo","Personal"),
    (["sephora","sally beauty","body shop","kiehl","mac cosmetics","lush","rituals","ulta","perfumeria","perfume"],"Cuidado personal","Personal"),
    # ── DIVERSIÓN ──
    (["cinepolis","cinemex","cine "],"Cine","Diversión"),
    (["ticketmaster","superboletos","eticket"],"Conciertos","Diversión"),
    (["teatro","concierto","evento","antro","bar "],"Salidas","Diversión"),
    # ── VACACIONES ──
    (["hotel","airbnb","booking","expedia","despegar","volaris","aeromexico","vivaaerobus","viva aerobus","trivago","hospedaje"],"Vacaciones","Vacaciones"),
    # ── EDUCACIÓN ──
    (["udemy","coursera","platzi","domestika","masterclass","skillshare"],"Cursos","Educación"),
    (["libreria","gandhi","gonvill","el sotano","libro"],"Libros","Educación"),
    # ── DEPARTAMENTO ──
    (["ikea","home store","mueble"],"Muebles","Departamento"),
    # ── OTROS / marketplaces (amazon al final: "prime video" gana en streaming) ──
    (["amazon","mercado libre","mercadolibre","aliexpress","temu","shopee"],"Otros","Otros"),
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
    "super farmacia":"Farmacia Guadalajara","farmacia guadalajara":"Farmacia Guadalajara",
    "farmacias guadalajara":"Farmacia Guadalajara","farmacias del ahorro":"Farmacias del Ahorro",
    "farmacia benavides":"Farmacia Benavides","farmacias similares":"Farmacia Similares",
    "starbucks":"Starbucks","mcdonald":"McDonalds","burger king":"Burger King","kfc":"KFC",
    "subway":"Subway","domino":"Dominos","little caesar":"Little Caesars","carls jr":"Carl's Jr",
    "uber eats":"Uber Eats","rappi":"Rappi","cinepolis":"Cinepolis","cinemex":"Cinemex",
    "shell":"Shell","pemex":"Pemex","bp ":"BP","mobil":"Mobil",
}

def normalizar_comercio(concepto: str) -> str:
    """Si el concepto contiene un comercio conocido, devuelve su nombre canónico.
    Se aplica en ambos flujos de ticket (Groq y Vision)."""
    if not concepto:
        return concepto
    c = normalizar(concepto)
    for clave, nombre in COMERCIOS_OCR.items():
        if normalizar(clave) in c:
            return nombre
    return concepto

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

    prompt = f"""Analiza este ticket o recibo de compra y extrae los datos. Hoy es {hoy.strftime('%d/%m/%Y')}.

Responde SOLO con JSON válido, sin texto adicional, sin markdown:
{{
  "concepto": "nombre del comercio en Title Case (ej: Walmart, Oxxo, Starbucks)",
  "monto": número con decimales (el TOTAL A PAGAR final, no subtotal ni total de artículos),
  "fecha": "YYYY-MM-DD",
  "productos": [{{"nombre": "nombre del producto", "precio": número}}]
}}

Reglas:
- El monto debe ser el total final que se pagó, incluyendo IVA.
- Si hay varios totales, elige el mayor que sea claramente el total de la compra.
- Si no puedes leer la fecha, usa {hoy.strftime('%Y-%m-%d')}.
- Si no reconoces el comercio, describe brevemente qué tipo de negocio es.
- En "productos" lista cada artículo comprado con su precio individual, tal como aparece en el ticket.
  Limpia nombres abreviados a algo legible cuando sea obvio. Si el ticket no tiene desglose de
  productos (ej: un recibo de pago o voucher), devuelve "productos": []."""

    raw = groq_vision(image_bytes, prompt, max_tokens=900)
    data = _extraer_json(raw)
    if not data:
        return None

    try:
        concepto = data.get("concepto", "").strip()
        monto = data.get("monto")
        fecha_str = data.get("fecha", hoy.strftime("%Y-%m-%d"))

        if not concepto or monto is None:
            return None

        try:
            fecha = datetime.date.fromisoformat(fecha_str)
        except (ValueError, TypeError):
            fecha = hoy

        productos = []
        for p in (data.get("productos") or []):
            try:
                nombre = str(p.get("nombre", "")).strip()
                precio = p.get("precio")
                precio = float(precio) if precio is not None else None
                if nombre:
                    productos.append({"nombre": nombre[:100], "precio": precio})
            except (ValueError, TypeError, AttributeError):
                continue

        return {"concepto": normalizar_comercio(concepto.title()), "monto": float(monto),
                "fecha": fecha, "productos": productos[:50]}
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

def cargar_historial_compartido():
    """Carga los últimos MAX_HISTORIAL gastos de ambos usuarios (sin filtrar por UsuarioID).
    Usado por /corregir para que cualquier usuario pueda ver y corregir los gastos recientes."""
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_HISTORIAL_ID}/query",
            headers=nh(),
            json={
                "filter": {"property": "UsuarioID", "number": {"greater_than": 0}},
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
        logger.error(f"Error cargando historial compartido: {ex}")
    return []

# ── METAS ────────────────────────────────────────────────────────────────────

def _buscar_meta_page(uid: int, presupuesto: str, ciclo: str) -> str | None:
    """Retorna el page_id de una meta existente (uid/presupuesto/ciclo), o None."""
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_METAS_ID}/query",
            headers=nh(),
            json={"filter": {"and": [
                {"property": "UsuarioID", "number":    {"equals": uid}},
                {"property": "Presupuesto", "rich_text": {"equals": presupuesto}},
                {"property": "Ciclo",       "rich_text": {"equals": ciclo}},
            ]}, "page_size": 1},
            timeout=NOTION_T_SHORT)
        if r and r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return results[0]["id"].replace("-", "")
    except Exception as ex:
        logger.error(f"Error buscando meta: {ex}")
    return None

def guardar_meta(uid: int, presupuesto: str, limite: float, ciclo: str) -> bool:
    """Guarda o actualiza una meta en Metas Bot. Upsert por uid/presupuesto/ciclo."""
    props = {
        "Titulo":      {"title":     [{"text": {"content": f"Meta {presupuesto} {ciclo}"}}]},
        "Presupuesto": {"rich_text": [{"text": {"content": presupuesto}}]},
        "Limite":      {"number": limite},
        "Ciclo":       {"rich_text": [{"text": {"content": ciclo}}]},
        "UsuarioID":   {"number": uid},
    }
    try:
        pid = _buscar_meta_page(uid, presupuesto, ciclo)
        if pid:
            r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{pid}",
                               headers=nh(), json={"properties": props}, timeout=NOTION_T_SHORT)
        else:
            r = notion_request("POST", f"{NOTION_API_BASE}/pages",
                               headers=nh(),
                               json={"parent": {"database_id": NOTION_METAS_ID}, "properties": props},
                               timeout=NOTION_T_SHORT)
        return bool(r and r.status_code in (200, 201))
    except Exception as ex:
        logger.error(f"Error guardando meta: {ex}")
        return False

def cargar_meta(uid: int, presupuesto: str, ciclo: str) -> float | None:
    """Carga el límite de una meta específica. None si no existe."""
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_METAS_ID}/query",
            headers=nh(),
            json={"filter": {"and": [
                {"property": "UsuarioID",   "number":    {"equals": uid}},
                {"property": "Presupuesto", "rich_text": {"equals": presupuesto}},
                {"property": "Ciclo",       "rich_text": {"equals": ciclo}},
            ]}, "page_size": 1},
            timeout=NOTION_T_SHORT)
        if r and r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return results[0]["properties"].get("Limite", {}).get("number")
    except Exception as ex:
        logger.error(f"Error cargando meta: {ex}")
    return None

def cargar_metas_ciclo(uid: int, ciclo: str) -> list:
    """Carga todas las metas del usuario para un ciclo dado."""
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_METAS_ID}/query",
            headers=nh(),
            json={"filter": {"and": [
                {"property": "UsuarioID", "number":    {"equals": uid}},
                {"property": "Ciclo",     "rich_text": {"equals": ciclo}},
            ]}},
            timeout=NOTION_T_SHORT)
        if r and r.status_code == 200:
            return [{"presupuesto": notion_rich_text(e["properties"], "Presupuesto"),
                     "limite":      e["properties"].get("Limite", {}).get("number", 0) or 0}
                    for e in r.json().get("results", [])]
    except Exception as ex:
        logger.error(f"Error cargando metas ciclo: {ex}")
    return []

# RAM: desglose de recurrentes de la última apertura (para el botón "Ver desglose")
_desglose_apertura: dict = {}

async def enviar_propuesta_mes(datos: dict):
    """Envía el mensaje de apertura de ciclo a ambos usuarios con botones de aprobación."""
    app = get_app()
    if not app:
        return

    ciclo_nuevo     = datos.get("ciclo_nuevo", "")
    ciclo_anterior  = datos.get("ciclo_anterior", "")
    total_anterior  = float(datos.get("total_anterior", 0))
    promedio_3m     = float(datos.get("promedio_3m", total_anterior))
    delta_pct       = float(datos.get("delta_pct", 0))
    recurrentes_n   = int(datos.get("recurrentes_registrados", 0))
    recurrentes_t   = float(datos.get("recurrentes_total", 0))
    limite_prop     = float(datos.get("limite_propuesto", promedio_3m))
    desglose        = datos.get("desglose", "")

    signo = "+" if delta_pct >= 0 else ""
    texto = (
        f"🆕 *{ciclo_nuevo} abierto*\n\n"
        f"📊 *{ciclo_anterior}* cerró en *${total_anterior:,.0f}*\n"
        f"   Promedio 3 meses: ${promedio_3m:,.0f} ({signo}{delta_pct:.1f}%)\n\n"
        f"🔁 Recurrentes registrados: {recurrentes_n} · ${recurrentes_t:,.0f}\n\n"
        f"🎯 Meta sugerida para *{ciclo_nuevo}*: *${limite_prop:,.0f}*\n\n"
        f"¿La confirmamos?"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Meta ${limite_prop:,.0f}", callback_data=f"propuesta_ok:{ciclo_nuevo}:{limite_prop:.0f}"),
        InlineKeyboardButton("❌ Sin meta",                  callback_data="propuesta_skip"),
    ], [
        InlineKeyboardButton("📋 Ver desglose",              callback_data=f"propuesta_ver:{ciclo_anterior}"),
    ]])

    if desglose:
        _desglose_apertura[ciclo_anterior] = desglose

    for uid in USUARIOS_AUTORIZADOS:
        try:
            await app.bot.send_message(chat_id=uid, text=texto, reply_markup=kb, parse_mode="Markdown")
        except Exception as ex:
            logger.error(f"Error enviando propuesta a {uid}: {ex}")

async def callback_propuesta(update, context):
    """Maneja los botones de la propuesta de apertura de ciclo."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if uid not in USUARIOS_AUTORIZADOS:
        return

    data = query.data

    if data.startswith("propuesta_ok:"):
        partes = data.split(":")
        ciclo  = partes[1] if len(partes) > 1 else ""
        try:
            limite = float(partes[2]) if len(partes) > 2 else 0.0
        except ValueError:
            limite = 0.0
        ok = await asyncio.get_event_loop().run_in_executor(None, guardar_meta, uid, "TOTAL", limite, ciclo)
        if ok:
            await query.edit_message_text(
                f"✅ *Meta guardada: ${limite:,.0f}* para {ciclo}\n\n"
                f"Te aviso cuando llegues al 80% y al 100%.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("❌ No pude guardar la meta. Intenta más tarde.")

    elif data == "propuesta_skip":
        await query.edit_message_text(
            "👌 Sin meta este ciclo. Puedes fijar una en cualquier momento diciendo\n"
            "\"quiero gastar máximo $X\" o \"meta Diversión 10000\"."
        )

    elif data.startswith("propuesta_ver:"):
        ciclo_ant = data.split(":", 1)[1]
        desglose  = _desglose_apertura.get(ciclo_ant)
        if desglose:
            await query.answer(text=desglose[:200], show_alert=True)
        else:
            await query.answer(text="Sin desglose disponible.", show_alert=True)

# ── ALIASES ──────────────────────────────────────────────────────────────────

_alias_cache: dict[int, list] = {}
_ALIAS_DEF_RE = re.compile(
    r'recuerda\s+que|cuando\s+digo|de\s+ahora\s+en\s+adelante|guarda\s+que|sabe\s+que',
    re.IGNORECASE
)

def _cargar_aliases_uid(uid: int) -> list:
    """Carga aliases del usuario desde Notion, con caché en RAM (invalidada al guardar)."""
    if uid in _alias_cache:
        return _alias_cache[uid]
    try:
        r = notion_request("POST",
            f"{NOTION_API_BASE}/databases/{NOTION_ALIAS_ID}/query",
            headers=nh(),
            json={"filter": {"property": "UsuarioID", "number": {"equals": uid}}},
            timeout=NOTION_T_SHORT)
        if r and r.status_code == 200:
            result = []
            for e in r.json().get("results", []):
                p = e["properties"]
                titulo = p.get("Trigger", {}).get("title", [])
                trigger = titulo[0].get("text", {}).get("content", "").lower() if titulo else ""
                resolved = notion_rich_text(p, "Resolved")
                if trigger and resolved:
                    result.append({"trigger": trigger, "resolved": resolved,
                                   "id": e["id"].replace("-", "")})
            _alias_cache[uid] = result
            return result
    except Exception as ex:
        logger.error(f"Error cargando aliases: {ex}")
    _alias_cache[uid] = []
    return []

def guardar_alias(uid: int, trigger: str, resolved: str) -> bool:
    """Upsert de alias en Notion (por trigger normalizado). Invalida la caché."""
    trigger_norm = trigger.lower().strip()
    existing_id  = next((a["id"] for a in _cargar_aliases_uid(uid)
                         if a["trigger"] == trigger_norm), None)
    props = {
        "Trigger":   {"title":     [{"text": {"content": trigger_norm}}]},
        "Resolved":  {"rich_text": [{"text": {"content": resolved.strip()}}]},
        "UsuarioID": {"number": uid},
    }
    try:
        if existing_id:
            r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{existing_id}",
                               headers=nh(), json={"properties": props}, timeout=NOTION_T_SHORT)
        else:
            r = notion_request("POST", f"{NOTION_API_BASE}/pages",
                               headers=nh(),
                               json={"parent": {"database_id": NOTION_ALIAS_ID}, "properties": props},
                               timeout=NOTION_T_SHORT)
        ok = bool(r and r.status_code in (200, 201))
        if ok:
            _alias_cache.pop(uid, None)  # invalidar caché para que recargue el siguiente uso
        return ok
    except Exception as ex:
        logger.error(f"Error guardando alias: {ex}")
        return False

def borrar_alias(uid: int, trigger: str) -> bool:
    """Elimina un alias por trigger. Retorna True si lo encontró y borró."""
    trigger_norm = trigger.lower().strip()
    alias_id = next((a["id"] for a in _cargar_aliases_uid(uid) if a["trigger"] == trigger_norm), None)
    if not alias_id:
        return False
    try:
        r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{alias_id}",
                           headers=nh(), json={"archived": True}, timeout=NOTION_T_SHORT)
        ok = bool(r and r.status_code == 200)
        if ok:
            _alias_cache.pop(uid, None)
        return ok
    except Exception as ex:
        logger.error(f"Error borrando alias: {ex}")
        return False

def expandir_aliases(uid: int, texto: str) -> str:
    """Reemplaza triggers conocidos del usuario en el texto antes de procesar.
    No expande si el mensaje ES una definición de alias (evita sustituciones recursivas)."""
    if _ALIAS_DEF_RE.search(texto):
        return texto
    aliases = _cargar_aliases_uid(uid)
    if not aliases:
        return texto
    # Sustituir de más largo a más corto para evitar reemplazos parciales
    for a in sorted(aliases, key=lambda x: len(x["trigger"]), reverse=True):
        texto = re.sub(re.escape(a["trigger"]), a["resolved"], texto, flags=re.IGNORECASE)
    return texto

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

# ── CLASIFICACIÓN + PARSEO CON GROQ (LLM) ─────────────────────────────────────
TARJETAS_VALIDAS = ["BBVA05", "BBVA12", "HEYB25", "BMEX04", "EFVO"]

TARJETA_EMOJI = {
    "BBVA05": "🔵",   # BBVA azul, corte día 5
    "BBVA12": "🔵",   # BBVA azul, corte día 12
    "HEYB25": "🟣",   # Hey Banco, morado
    "BMEX04": "🔴",   # Banorte, rojo
    "EFVO":   "💵",   # Efectivo
}

SC_EMOJI = {
    # Automovil
    "Gasolina": "⛽", "Estacionamento": "🅿️", "Mantenimiento": "🔧",
    "VW POLO": "🚗", "Seguro Auto": "🛡️",
    # Personal
    "Ropa": "👕", "Calzado": "👟", "Doctor": "🩺", "Medicina": "💊",
    "Gimnasio": "🏋️", "Corte de pelo": "✂️", "Cuidado personal": "🧴",
    "Gasto personal": "👤",
    # Despensa
    "Super": "🛒", "Abarrotes": "🥫", "Carniceria": "🥩", "Mercado": "🏪",
    "Comida": "🍱",
    # Deudas
    "MSI": "💳", "Deudas": "🏦", "EFI": "🏦", "DBMEX": "🏦",
    "PDHB25": "🏦", "PRP": "🏦", "Impuestos": "📊",
    # Diversión
    "Salidas": "🎊", "Treat": "🍭", "Cine": "🎬", "Conciertos": "🎵",
    "Tiempo de calidad": "❤️",
    # Educación
    "Libros": "📖", "Cursos": "🎓",
    # Emergencias
    "Emergencias": "🚨",
    # Ezra
    "Ezra": "👶",
    # Generosidad
    "Regalos": "🎁", "Ofrenda": "🙏", "Diezmo": "⛪",
    # Iglesia
    "Iglesia": "⛪",
    # Otros
    "Otros": "📦", "Vacaciones": "🏖️",
    # Restaurantes
    "Restaurantes": "🍽️",
    # Servicios
    "Servicios": "⚡", "Streaming": "📺", "Internet": "🌐",
    "Telefonia Celular": "📱", "Luz": "💡", "Agua": "💧",
    # Departamento
    "Renta": "🏠", "Muebles": "🛋️", "Decoracion": "🖼️",
}

def clasificar_mensaje_groq(texto: str, ultimo: dict = None, historial: list = None):
    """
    Clasifica un mensaje con Groq/Llama 3.3 70B. Devuelve (tipo, payload):
      - ("gasto", gasto_dict)        → registrar un gasto nuevo
      - ("multi_gasto", [gastos])    → registrar varios gastos
      - ("consulta", None)           → pregunta sobre finanzas/gastos
      - ("edicion", campos_dict)     → modificar el último gasto (solo si `ultimo` existe)
      - ("otro", None)               → saludo/charla
      - (None, None)                 → Groq falló / no parseable
    `ultimo`: último gasto del usuario (para habilitar la opción de edición).
    `historial`: últimos turnos de la conversación (para resolver referencias como "¿y ayer?").
    """
    if not GROQ_API_KEY:
        return (None, None)

    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()

    bloque_historial = ""
    if historial:
        ctx = "\n".join(f"{m['role']}: {m['content']}" for m in historial[-4:])
        bloque_historial = (
            f"\nContexto reciente de la conversación (úsalo para resolver referencias como "
            f"\"¿y ayer?\", \"¿y en esa categoría?\", \"¿cuánto fue?\"):\n{ctx}\n"
        )

    bloque_edicion = ""
    if ultimo:
        bloque_edicion = f"""
- Si el usuario quiere MODIFICAR el último gasto registrado (usa "cámbialo", "ponlo en", "era", "más bien", "corrige"):
{{"tipo": "edicion", "monto": número o null, "concepto": texto o null, "tarjeta": "{'/'.join(TARJETAS_VALIDAS)} o null", "fecha": "YYYY-MM-DD o null", "presupuesto": "un presupuesto exacto de la lista o null", "subcategoria": "una subcategoría exacta de la lista o null"}}
  (incluye SOLO los campos que el usuario pide cambiar; el resto null)
  Si el usuario dice "pagué en efectivo" / "no usé tarjeta" / "fue en efectivo" → tarjeta: "EFVO".
  Último gasto: {ultimo.get('concepto')} ${ultimo.get('monto')} — {ultimo.get('subcategoria')}/{ultimo.get('presupuesto')}
  Presupuestos válidos: {', '.join(PR.keys())}
  Subcategorías válidas: {', '.join(SC.keys())}
"""

    prompt = f"""Eres el clasificador de un bot de gastos en español mexicano. Hoy es {hoy.strftime('%d/%m/%Y')}.
{bloque_historial}
Mensaje del usuario: "{texto}"

Decide la intención y responde SOLO con JSON válido, sin texto adicional ni markdown:

- Si el usuario quiere REGISTRAR un gasto NUEVO (afirma haber gastado/comprado/pagado algo):
{{"tipo": "gasto", "concepto": "comercio o descripción corta en Title Case", "monto": número sin $, "fecha": "YYYY-MM-DD", "tarjeta": "{'/'.join(TARJETAS_VALIDAS)} o null"}}

- Si el usuario menciona DOS O MÁS gastos DISTINTOS en el mismo mensaje (ej. "fui al super 350 y cargué gasolina 500"):
{{"tipo": "multi_gasto", "gastos": [{{"concepto": "...", "monto": número, "fecha": "YYYY-MM-DD", "tarjeta": "{'/'.join(TARJETAS_VALIDAS)} o null"}}, ...]}}
  (un objeto por gasto, máximo 5; cada uno con su concepto y monto propios)

- Si el usuario PREGUNTA o CONSULTA sobre sus gastos/finanzas (cuánto, cuándo, en qué, comparar, totales, presupuestos), aunque mencione cantidades o categorías:
{{"tipo": "consulta"}}
{bloque_edicion}
- Si el usuario quiere FIJAR una META de gasto (usa "quiero gastar máximo", "meta de", "límite de", "no gastar más de", "meta 30000", "pon meta"):
{{"tipo": "meta", "presupuesto": "nombre exacto del presupuesto o TOTAL para meta global del ciclo", "limite": número}}
  Ej: "quiero gastar máximo 10000 en Diversión" → {{"tipo": "meta", "presupuesto": "Diversión", "limite": 10000}}
  Ej: "meta total 35000" → {{"tipo": "meta", "presupuesto": "TOTAL", "limite": 35000}}
  Ej: "pon meta Restaurantes 8000" → {{"tipo": "meta", "presupuesto": "Restaurantes", "limite": 8000}}
  Presupuestos válidos: {', '.join(PR.keys())} o TOTAL

- Si el usuario declara el INGRESO ESTIMADO del mes (usa "esperamos ganar", "vamos a ganar", "ingreso del mes", "ingreso estimado", "recibiremos", "nuestro ingreso"):
{{"tipo": "ingreso", "monto": número, "ciclo": "código MES+AA o null para el ciclo activo"}}
  Ej: "este mes esperamos ganar 45000" → {{"tipo": "ingreso", "monto": 45000, "ciclo": null}}
  Ej: "el ingreso de JUL26 es 52000" → {{"tipo": "ingreso", "monto": 52000, "ciclo": "JUL26"}}
  Ej: "actualizamos el ingreso a 38000" → {{"tipo": "ingreso", "monto": 38000, "ciclo": null}}

- Si el usuario quiere GUARDAR un atajo o alias personal (usa "recuerda que", "cuando digo", "de ahora en adelante", "guarda que"):
{{"tipo": "alias", "trigger": "frase que dice el usuario", "resolved": "lo que significa"}}
  Ej: "recuerda que el café de siempre es Starbucks BBVA05" → {{"tipo": "alias", "trigger": "el café de siempre", "resolved": "Starbucks BBVA05"}}
  Ej: "cuando digo el super es HEB" → {{"tipo": "alias", "trigger": "el super", "resolved": "HEB"}}
  Ej: "guarda que gasolina full = 700 BBVA12" → {{"tipo": "alias", "trigger": "gasolina full", "resolved": "700 BBVA12"}}

- Si el usuario quiere VER sus aliases ("¿qué atajos tengo?", "muéstrame mis aliases", "¿cuáles son mis atajos?"):
{{"tipo": "listar_aliases"}}

- Si el usuario quiere BORRAR un alias ("olvida el alias X", "borra el atajo X", "elimina el alias Y"):
{{"tipo": "borrar_alias", "trigger": "frase exacta del alias a borrar"}}

- Si el usuario pide GENERAR UN REPORTE ("genera el reporte", "dame el reporte semanal", "reporte mensual"):
{{"tipo": "reporte", "subtipo": "semanal"}}  o  {{"tipo": "reporte", "subtipo": "mensual"}}

- Si el usuario quiere EJECUTAR UNA ACCIÓN MASIVA sobre gastos existentes (reclasificar, renombrar, cambiar tarjeta, borrar en bulk, ver sin categoría, etc.):
{{"tipo": "accion",
  "operacion": "reclasificar|renombrar|cambiar_tarjeta|borrar_chicos|sin_categoria|crear_meta_auto|cierre_ciclo",
  "filtro_concepto": "texto a buscar en el concepto (ej. 'uber')" | null,
  "filtro_subcategoria": "subcategoría EXACTA de la lista" | null,
  "filtro_tarjeta": "BBVA05|BBVA12|HEYB25|BMEX04|EFVO" | null,
  "filtro_monto_max": número | null,
  "nueva_subcategoria": "subcategoría EXACTA destino" | null,
  "nuevo_presupuesto": "presupuesto EXACTO destino" | null,
  "nuevo_concepto": "texto destino" | null,
  "nueva_tarjeta": "BBVA05|BBVA12|HEYB25|BMEX04|EFVO" | null,
  "meses": ["MAY26"] | null
}}
  Operaciones:
  - "reclasificar": cambiar subcategoría (y opcionalmente presupuesto) a gastos que coincidan
  - "renombrar": cambiar el concepto de gastos que coincidan
  - "cambiar_tarjeta": mover gastos de una tarjeta a otra
  - "borrar_chicos": archivar/eliminar gastos pequeños (usa filtro_monto_max)
  - "sin_categoria": mostrar gastos sin subcategoría asignada
  - "crear_meta_auto": analizar el ciclo y proponer/crear una meta para la categoría con más gasto
  - "cierre_ciclo": resumen del ciclo + archivar todos sus gastos
  Presupuestos válidos: {', '.join(PR.keys())}
  Subcategorías válidas: {', '.join(SC.keys())}

- Si es un saludo, charla o algo no relacionado:
{{"tipo": "otro"}}

Reglas para "gasto":
- Concepto conciso: "Starbucks", "Super", "Comida", "Gasolina".
- "ayer" resta 1 día a hoy. Sin fecha = hoy.
- Montos aproximados ("como 350", "unos 400") → usa ese número. Dos montos del MISMO gasto → el mayor.
- Si el usuario menciona "efectivo", "en efectivo", "cash", "no usé tarjeta", "pagué en efectivo" → tarjeta: "EFVO". NO incluir la palabra "efectivo" en el concepto.
- Si el usuario menciona "efectivo" en el contexto de edición → campo tarjeta: "EFVO".
IMPORTANTE: si hay duda y el mensaje tiene forma de pregunta, elige "consulta". Nunca registres un gasto cuando el usuario está preguntando.
IMPORTANTE: usa "multi_gasto" SOLO si hay 2+ gastos claramente distintos. Si es un solo gasto (aunque mencione varios montos o productos), usa "gasto"."""

    raw = groq_completar(prompt, max_tokens=250)
    data = _extraer_json(raw)
    if not data:
        return (None, None)

    try:
        tipo = data.get("tipo")

        if tipo == "consulta":
            return ("consulta", None)
        if tipo == "meta":
            presupuesto = (data.get("presupuesto") or "TOTAL").strip()
            try:
                limite = float(data.get("limite") or 0)
            except (ValueError, TypeError):
                return ("otro", None)
            return ("meta", {"presupuesto": presupuesto, "limite": limite}) if limite > 0 else ("otro", None)
        if tipo == "ingreso":
            try:
                monto_i = float(data.get("monto") or 0)
            except (ValueError, TypeError):
                return ("otro", None)
            ciclo_i = (data.get("ciclo") or "").strip().upper() or None
            return ("ingreso", {"monto": monto_i, "ciclo": ciclo_i}) if monto_i > 0 else ("otro", None)
        if tipo == "alias":
            trigger  = (data.get("trigger")  or "").strip()
            resolved = (data.get("resolved") or "").strip()
            return ("alias", {"trigger": trigger, "resolved": resolved}) if (trigger and resolved) else ("otro", None)
        if tipo == "listar_aliases":
            return ("listar_aliases", None)
        if tipo == "borrar_alias":
            trigger = (data.get("trigger") or "").strip().lower()
            return ("borrar_alias", {"trigger": trigger}) if trigger else ("otro", None)
        if tipo == "reporte":
            subtipo = (data.get("subtipo") or "semanal").lower()
            subtipo = "mensual" if "mens" in subtipo else "semanal"
            return ("reporte", {"subtipo": subtipo})
        if tipo == "accion":
            operacion = (data.get("operacion") or "").strip().lower()
            if not operacion:
                return ("otro", None)
            payload_accion = {
                "operacion": operacion,
                "filtro_concepto":    (data.get("filtro_concepto")    or "").strip() or None,
                "filtro_subcategoria":(data.get("filtro_subcategoria") or "").strip() or None,
                "filtro_tarjeta":     (data.get("filtro_tarjeta")     or "").strip().upper() or None,
                "filtro_monto_max":   data.get("filtro_monto_max"),
                "nueva_subcategoria": (data.get("nueva_subcategoria") or "").strip() or None,
                "nuevo_presupuesto":  (data.get("nuevo_presupuesto")  or "").strip() or None,
                "nuevo_concepto":     (data.get("nuevo_concepto")     or "").strip() or None,
                "nueva_tarjeta":      (data.get("nueva_tarjeta")      or "").strip().upper() or None,
                "meses":              [m.upper() for m in (data.get("meses") or [])],
            }
            return ("accion", payload_accion)
        if tipo == "edicion" and ultimo:
            campos = {k: data.get(k) for k in
                      ("monto", "concepto", "tarjeta", "fecha", "presupuesto", "subcategoria")
                      if data.get(k) not in (None, "", "null")}
            return ("edicion", campos) if campos else ("otro", None)
        if tipo == "multi_gasto":
            items = data.get("gastos") or []
            gastos = [g for g in (_construir_gasto_desde_data(it, hoy) for it in items[:5]) if g]
            if len(gastos) >= 2:
                return ("multi_gasto", gastos)
            if len(gastos) == 1:
                return ("gasto", gastos[0])
            return (None, None)
        if tipo != "gasto":
            return ("otro", None)

        g = _construir_gasto_desde_data(data, hoy)
        return ("gasto", g) if g else (None, None)
    except Exception as e:
        logger.warning(f"Groq clasificación fallida: {e} — texto: {texto[:80]}")
        return (None, None)

def _construir_gasto_desde_data(data: dict, hoy) -> dict | None:
    """Arma un gasto completo desde {concepto, monto, fecha, tarjeta} del LLM. None si inválido."""
    concepto = (data.get("concepto") or "").strip()
    monto = data.get("monto")
    if not concepto or monto is None:
        return None
    try:
        monto = float(monto)
    except (ValueError, TypeError):
        return None
    try:
        fecha = datetime.date.fromisoformat(data.get("fecha") or hoy.strftime("%Y-%m-%d"))
    except (ValueError, TypeError):
        fecha = hoy
    tarjeta_raw = data.get("tarjeta")
    tarjeta = calcular_tarjeta(fecha, tarjeta_raw if tarjeta_raw in TARJETAS_VALIDAS else None)
    mes = calcular_mes(fecha, tarjeta)
    sub, pre, seguro = inferir_categoria(concepto)
    return {
        "concepto": concepto.title(), "monto": monto,
        "fecha": fecha.strftime("%Y-%m-%d"), "tarjeta": tarjeta, "mes": mes,
        "subcategoria": sub, "presupuesto": pre, "seguro": seguro,
    }

def _parece_gasto_estricto(texto: str) -> bool:
    """
    Retorna True si el texto ya tiene formato estricto (Concepto Monto [opcional])
    y NO necesita LLM. Ahorra llamadas a la API.
    Ejemplos estrictos: "Oxxo 45", "Starbucks 150 BBVA05", "Super 350 ayer"
    Mensajes naturales largos (voz, NL) siempre van a Groq aunque terminen en número.
    """
    tokens = texto.strip().split()
    if len(tokens) < 2:
        return False
    if len(tokens) > 9:   # mensaje largo → casi seguro es lenguaje natural
        return False
    for t in tokens[-3:]:
        try:
            float(t.replace("$", "").replace(",", ""))
            return True
        except ValueError:
            pass
    return False

def _leer_tarjeta(props: dict) -> str:
    """Lee el valor de tarjeta de un gasto de Notion.
    Orden de prioridad: Pago (select) → Estado de Cuenta (rich_text) → Tarjeta (rich_text).
    El bot escribe a 'Estado de Cuenta' + 'Pago'; gastos manuales pueden usar 'Tarjeta'.
    """
    sel = props.get("Pago", {}).get("select")
    if sel and sel.get("name"):
        return sel["name"]
    for campo in ("Estado de Cuenta", "Tarjeta"):
        val = "".join(rt.get("plain_text", "")
                      for rt in props.get(campo, {}).get("rich_text", []))
        if val:
            return val
    return ""

def _presupuesto_de_props(props) -> str:
    """Resuelve el nombre del presupuesto (PR) de un gasto de Notion, o '' si no tiene."""
    rel = props.get("Presupuesto", {}).get("relation", [])
    if rel:
        pr_id = rel[0].get("id", "").replace("-", "")
        nombre = next((k for k, v in PR.items() if v == pr_id), "")
        if nombre:
            return nombre
    # Respaldo: derivar el presupuesto desde la Subcategoria (que el usuario no borra)
    return _presupuesto_desde_subcat(props)

def _presupuesto_desde_subcat(props) -> str:
    """Deriva el presupuesto desde la relación Subcategoria, vía SUBCAT_PRESUPUESTO."""
    rel = props.get("Subcategoria", {}).get("relation", [])
    if not rel:
        return ""
    sc_id = rel[0].get("id", "").replace("-", "")
    nombre_sc = next((k for k, v in SC.items() if v == sc_id), "")
    return SUBCAT_PRESUPUESTO.get(nombre_sc, "")

def ejecutar_consulta_finanzas(plan: dict) -> dict:
    """
    Ejecuta un plan de consulta determinístico contra Notion.
    plan: {"meses": [...], "categoria": str|None, "subcategoria": str|None, "comercio": str|None,
           "fecha_desde": "YYYY-MM-DD"|None, "fecha_hasta": "YYYY-MM-DD"|None,
           "historico": bool}
    Si historico=True, consulta TODOS los registros desde 2020 (sin límite de meses).
    Si fecha_desde/hasta están presentes, filtra por Fecha real (no por ciclo de mes).
    Devuelve un agregado compacto. Es la ÚNICA función que toca datos para consultas NL.
    """
    categoria       = (plan.get("categoria")    or "").strip() or None
    subcategoria    = (plan.get("subcategoria") or "").strip() or None
    subcategoria_id = SC.get(subcategoria, "").replace("-", "") if subcategoria else None
    tarjeta_filtro  = (plan.get("tarjeta")      or "").strip().upper() or None
    comercio        = normalizar(plan.get("comercio") or "") or None
    fecha_desde     = (plan.get("fecha_desde") or "").strip() or None
    fecha_hasta     = (plan.get("fecha_hasta") or "").strip() or None
    historico       = bool(plan.get("historico"))

    res = {"meses": [], "total": 0.0, "conteo": 0,
           "por_dia": {}, "por_mes": {}, "por_categoria": {}, "top": [],
           "gastos_raw": [],
           "fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta,
           "historico": historico}
    todos = []

    if historico:
        # ── Ruta histórica completa ──────────────────────────────────────────
        # Consulta todos los registros desde 2020 sin límite de ciclo de mes.
        hoy_iso = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
        filtro_notion = {"and": [
            {"property": "Fecha", "date": {"on_or_after": "2020-01-01"}},
            {"property": "Fecha", "date": {"on_or_before": hoy_iso}}
        ]}
        gastos = query_notion_db(NOTION_DATABASE_ID, filtro_notion)
        for g in gastos:
            props = g.get("properties", {})
            monto = props.get("Monto", {}).get("number", 0) or 0
            pr    = _presupuesto_de_props(props)
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            fecha    = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
            if categoria and pr != categoria:
                continue
            if subcategoria_id:
                rel_sc = props.get("Subcategoria", {}).get("relation", [])
                if not any(r.get("id", "").replace("-", "") == subcategoria_id for r in rel_sc):
                    continue
            if tarjeta_filtro:
                t_notion = _leer_tarjeta(props).upper()
                if tarjeta_filtro not in t_notion:
                    continue
            if comercio and comercio not in normalizar(concepto):
                continue
            res["total"] += monto
            res["conteo"] += 1
            anio = fecha[:4] if fecha else "?"
            res["por_mes"][anio] = res["por_mes"].get(anio, 0) + monto
            if pr:
                res["por_categoria"][pr] = res["por_categoria"].get(pr, 0) + monto
            todos.append((concepto, monto, fecha, anio))
            res["gastos_raw"].append({"concepto": concepto, "monto": monto, "fecha": fecha,
                                      "notion_id": g.get("id", "").replace("-", "")})
    elif fecha_desde or fecha_hasta:
        # ── Ruta por fecha real ──────────────────────────────────────────
        # Filtra directamente por la propiedad Fecha de Notion (ignora ciclo de mes).
        filtros = []
        if fecha_desde:
            filtros.append({"property": "Fecha", "date": {"on_or_after":  fecha_desde}})
        if fecha_hasta:
            filtros.append({"property": "Fecha", "date": {"on_or_before": fecha_hasta}})
        filtro_notion = {"and": filtros} if len(filtros) > 1 else filtros[0]
        gastos = query_notion_db(NOTION_DATABASE_ID, filtro_notion)
        for g in gastos:
            props = g.get("properties", {})
            monto = props.get("Monto", {}).get("number", 0) or 0
            pr    = _presupuesto_de_props(props)
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            fecha    = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
            if categoria and pr != categoria:
                continue
            if subcategoria_id:
                rel_sc = props.get("Subcategoria", {}).get("relation", [])
                if not any(r.get("id", "").replace("-", "") == subcategoria_id for r in rel_sc):
                    continue
            if tarjeta_filtro:
                t_notion = _leer_tarjeta(props).upper()
                if tarjeta_filtro not in t_notion:
                    continue
            if comercio and comercio not in normalizar(concepto):
                continue
            res["total"] += monto
            res["conteo"] += 1
            dia = fecha[:10] if fecha else "?"
            res["por_dia"][dia]  = res["por_dia"].get(dia, 0) + monto
            if pr:
                res["por_categoria"][pr] = res["por_categoria"].get(pr, 0) + monto
            todos.append((concepto, monto, fecha, dia))
            res["gastos_raw"].append({"concepto": concepto, "monto": monto, "fecha": fecha,
                                      "notion_id": g.get("id", "").replace("-", "")})
    else:
        # ── Ruta por ciclo de mes (comportamiento original) ──────────────
        meses = [m.upper() for m in (plan.get("meses") or [])][:6] or [mes_activo_str()]
        res["meses"] = meses
        for mes in meses:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            gastos = query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}})
            for g in gastos:
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                pr    = _presupuesto_de_props(props)
                titulo = props.get("Concepto", {}).get("title", [])
                concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
                fecha    = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
                if categoria and pr != categoria:
                    continue
                if subcategoria_id:
                    rel_sc = props.get("Subcategoria", {}).get("relation", [])
                    if not any(r.get("id", "").replace("-", "") == subcategoria_id for r in rel_sc):
                        continue
                if tarjeta_filtro:
                    t_notion = _leer_tarjeta(props).upper()
                    if tarjeta_filtro not in t_notion:
                        continue
                if comercio and comercio not in normalizar(concepto):
                    continue
                res["total"] += monto
                res["conteo"] += 1
                res["por_mes"][mes] = res["por_mes"].get(mes, 0) + monto
                if pr:
                    res["por_categoria"][pr] = res["por_categoria"].get(pr, 0) + monto
                todos.append((concepto, monto, fecha, mes))
                res["gastos_raw"].append({"concepto": concepto, "monto": monto, "fecha": fecha,
                                          "notion_id": g.get("id", "").replace("-", "")})

    res["top"] = sorted(todos, key=lambda x: x[1], reverse=True)[:8]
    res["gastos_raw"] = sorted(res["gastos_raw"], key=lambda x: x["monto"], reverse=True)[:20]
    return res

def _formatear_datos_consulta(res: dict) -> str:
    if res["conteo"] == 0:
        return "Sin gastos que coincidan con la consulta."
    partes = []
    fd = res.get("fecha_desde") or ""
    fh = res.get("fecha_hasta") or ""
    if res.get("historico"):
        partes.append("Consulta histórica completa (desde 2020 hasta hoy)")
        if res.get("por_mes"):
            anios = sorted(res["por_mes"].items())
            partes.append("Por año: " + ", ".join(f"{a}=${v:,.0f}" for a, v in anios))
    elif fd or fh:
        if fd == fh and fd:
            partes.append(f"Fecha consultada: {fd}")
        else:
            partes.append(f"Período: {fd or '?'} → {fh or '?'}")
        if len(res.get("por_dia", {})) > 1:
            dias = sorted(res["por_dia"].items())
            partes.append("Por día: " + ", ".join(f"{d}=${v:,.0f}" for d, v in dias))
    else:
        partes.append(f"Meses consultados: {', '.join(res['meses'])}")
        if len(res["por_mes"]) > 1:
            partes.append("Por mes: " + ", ".join(f"{m}=${v:,.0f}" for m, v in res["por_mes"].items()))
    partes.append(f"Total: ${res['total']:,.0f}  ({res['conteo']} gastos)")
    if res["por_categoria"]:
        cats = sorted(res["por_categoria"].items(), key=lambda x: x[1], reverse=True)
        partes.append("Por categoría: " + ", ".join(f"{k}=${v:,.0f}" for k, v in cats))
    if res["top"]:
        partes.append("Gastos del período: " + "; ".join(
            f"{c} ${m:,.0f} ({_fecha_compacta(f)})" for c, m, f, _ in res["top"]))
    return "\n".join(partes)

def _agg_por_anio() -> dict:
    """Gasto total por año, leído de los rollups de la BD Balance (1 query, eficiente)."""
    if not NOTION_BALANCE_ID:
        return {}
    por_anio = {}
    for p in query_notion_db(NOTION_BALANCE_ID):
        props = p.get("properties", {})
        sel = props.get("Año", {}).get("select")
        anio = sel.get("name") if sel else None
        g = props.get("Gasto", {})
        total = (g.get("rollup", {}) or {}).get("number")
        if total is None:
            total = g.get("number")
        if anio and isinstance(total, (int, float)):
            por_anio[anio] = por_anio.get(anio, 0) + total
    return por_anio

def _gasto_extremo(propiedad: str, direccion: str):
    """Trae 1 gasto ordenado por una propiedad (más antiguo/reciente/caro). 1 query."""
    body = {"page_size": 1, "sorts": [{"property": propiedad, "direction": direccion}]}
    r = notion_request("POST", f"{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query",
                       headers=nh(), json=body, timeout=NOTION_T_DEFAULT)
    if not r or r.status_code != 200:
        return None
    res = r.json().get("results", [])
    if not res:
        return None
    props = res[0].get("properties", {})
    titulo = props.get("Concepto", {}).get("title", [])
    concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
    monto = props.get("Monto", {}).get("number", 0) or 0
    fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
    return {"concepto": concepto, "monto": monto, "fecha": fecha,
            "presupuesto": _presupuesto_de_props(props)}

def _meses_recientes(n: int) -> list:
    """Últimos n ciclos terminando en el mes activo (ej: [JUN26, MAY26, ABR26])."""
    meses, m = [], mes_activo_str()
    for _ in range(max(1, n)):
        meses.append(m)
        m = _mes_anterior(m)
    return meses

def _totales_por_ciclo() -> dict:
    """{codigo_mes: gasto_total} leído de los rollups de Balance (1 query)."""
    res = {}
    if not NOTION_BALANCE_ID:
        return res
    for p in query_notion_db(NOTION_BALANCE_ID):
        props = p.get("properties", {})
        code = ""
        for v in props.values():
            if v.get("type") == "title":
                t = v.get("title", [])
                code = t[0]["text"]["content"] if t else ""
                break
        g = props.get("Gasto", {})
        total = (g.get("rollup", {}) or {}).get("number")
        if total is None:
            total = g.get("number")
        if code and isinstance(total, (int, float)):
            res[code] = total
    return res

def _promedio_mensual() -> dict:
    """Promedio de gasto mensual sobre los ciclos con gasto > 0."""
    totales = [v for v in _totales_por_ciclo().values() if v > 0]
    if not totales:
        return {}
    return {"promedio": sum(totales) / len(totales), "meses": len(totales), "total": sum(totales)}

def _gastos_recientes(n_meses: int = 3, categoria: str = None, meses_especificos: list = None,
                      subcategoria_id: str = None) -> list:
    """Lista de (concepto, monto, fecha) de los últimos n ciclos.
    Si se pasa meses_especificos, usa esos en vez de los últimos n meses.
    Si se pasa categoria, filtra por presupuesto.
    Si se pasa subcategoria_id (ID limpio de SC), filtra por subcategoría.
    """
    items = []
    meses_a_consultar = meses_especificos if meses_especificos else _meses_recientes(n_meses)
    for mes in meses_a_consultar:
        mid = buscar_mes_id(mes)
        if not mid:
            continue
        for g in query_notion_db(NOTION_DATABASE_ID, {"property": "Mes", "relation": {"contains": mid}}):
            props = g.get("properties", {})
            monto = props.get("Monto", {}).get("number", 0) or 0
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
            if categoria:
                pr = _presupuesto_de_props(props)
                if pr != categoria:
                    continue
            if subcategoria_id:
                rel_sc = props.get("Subcategoria", {}).get("relation", [])
                if not any(r.get("id", "").replace("-", "") == subcategoria_id for r in rel_sc):
                    continue
            items.append((concepto, monto, fecha))
    return items

def _datos_consulta_especial(modo: str, plan: dict = None):
    """Devuelve el texto de datos para los modos de agregación especial, o None si no aplica.
    plan puede incluir 'categoria' y 'meses' para filtrar en modos que lo soporten.
    """
    plan = plan or {}
    categoria       = (plan.get("categoria")    or "").strip() or None
    subcategoria    = (plan.get("subcategoria") or "").strip() or None
    subcategoria_id = SC.get(subcategoria, "").replace("-", "") if subcategoria else None
    meses_plan      = [m.upper() for m in (plan.get("meses") or [])] or None

    if modo == "por_anio":
        pa = _agg_por_anio()
        if not pa:
            return "Sin datos de gasto por año."
        top = max(pa.items(), key=lambda x: x[1])
        detalle = ", ".join(f"{a}=${v:,.0f}" for a, v in sorted(pa.items()))
        return f"Gasto total por año: {detalle}. El año con MÁS gasto fue {top[0]} (${top[1]:,.0f})."
    if modo in ("primero", "ultimo", "mayor"):
        if modo == "primero":
            g, etq = _gasto_extremo("Fecha", "ascending"), "más antiguo registrado"
        elif modo == "ultimo":
            g, etq = _gasto_extremo("Fecha", "descending"), "más reciente"
        else:
            g, etq = _gasto_extremo("Monto", "descending"), "más caro de toda la historia"
        if not g:
            return "No encontré ese gasto."
        cat = f", categoría {g['presupuesto']}" if g.get("presupuesto") else ""
        return f"El gasto {etq}: '{g['concepto']}' por ${g['monto']:,.2f} el {g['fecha']}{cat}."
    if modo == "ranking_categorias":
        res = ejecutar_consulta_finanzas({"meses": meses_plan or _meses_recientes(3), "subcategoria": subcategoria})
        if res["conteo"] == 0:
            return "Sin gastos en los últimos 3 meses."
        cats = sorted(res["por_categoria"].items(), key=lambda x: x[1], reverse=True)
        detalle = ", ".join(f"{k}=${v:,.0f}" for k, v in cats[:8])
        return f"En qué se va el dinero (últimos 3 meses, {', '.join(res['meses'])}): {detalle}. Total ${res['total']:,.0f}."
    if modo == "promedio_mensual":
        if categoria:
            # Promedio mensual de una categoría específica
            meses_hist = _meses_recientes(12)
            totales_cat = []
            for mes in meses_hist:
                r = ejecutar_consulta_finanzas({"meses": [mes], "categoria": categoria, "subcategoria": subcategoria})
                if r["total"] > 0:
                    totales_cat.append(r["total"])
            if not totales_cat:
                return f"Sin gastos en {categoria} para calcular promedio."
            prom = sum(totales_cat) / len(totales_cat)
            return f"Promedio mensual en {categoria}: ${prom:,.0f} (sobre {len(totales_cat)} meses con registro)."
        d = _promedio_mensual()
        if not d:
            return "Sin datos para calcular el promedio."
        return f"Promedio de gasto mensual: ${d['promedio']:,.0f} (sobre {d['meses']} meses con registro)."
    if modo == "dia_semana":
        items = _gastos_recientes(3, categoria=categoria, meses_especificos=meses_plan, subcategoria_id=subcategoria_id)
        entre = sum(m for c, m, f in items if f and _es_finde(f) is False)
        finde = sum(m for c, m, f in items if f and _es_finde(f) is True)
        ce = sum(1 for c, m, f in items if f and _es_finde(f) is False)
        cf = sum(1 for c, m, f in items if f and _es_finde(f) is True)
        periodo = f" en {', '.join(meses_plan)}" if meses_plan else " (últimos 3 meses)"
        cat_str = f" en {categoria}" if categoria else ""
        return (f"Gastos{cat_str}{periodo} — Entre semana (lun-vie): ${entre:,.0f} en {ce} gastos. "
                f"Fines de semana (sáb-dom): ${finde:,.0f} en {cf} gastos.")
    if modo == "desviacion":
        activo = mes_activo_str()
        if categoria or subcategoria:
            # Comparar categoría/subcategoría en mes activo vs su promedio histórico
            meses_hist = _meses_recientes(7)
            totales_cat = {}
            for mes in meses_hist:
                r = ejecutar_consulta_finanzas({"meses": [mes], "categoria": categoria, "subcategoria": subcategoria})
                if r["total"] > 0:
                    totales_cat[mes] = r["total"]
            actual = totales_cat.get(activo, 0)
            otros = [v for k, v in totales_cat.items() if k != activo and v > 0]
            filtro_str = subcategoria or categoria
            if not otros:
                return f"Aún no tengo suficientes meses con gastos en {filtro_str} para comparar."
            prom = sum(otros) / len(otros)
            dif = actual - prom
            signo = "MÁS" if dif >= 0 else "MENOS"
            return (f"Mes activo ({activo}) en {filtro_str}: ${actual:,.0f}. "
                    f"Tu promedio histórico en {filtro_str}: ${prom:,.0f}. "
                    f"Estás gastando ${abs(dif):,.0f} {signo} que tu promedio.")
        tot = _totales_por_ciclo()
        actual = tot.get(activo, 0)
        otros = [v for k, v in tot.items() if k != activo and v > 0]
        if not otros:
            return "Aún no tengo suficientes meses para comparar."
        prom = sum(otros) / len(otros)
        dif = actual - prom
        signo = "MÁS" if dif >= 0 else "MENOS"
        return (f"Mes activo ({activo}): ${actual:,.0f}. Promedio de tus otros meses: ${prom:,.0f}. "
                f"Estás gastando ${abs(dif):,.0f} {signo} que tu promedio.")
    if modo == "hormiga":
        items = _gastos_recientes(3, categoria=categoria, meses_especificos=meses_plan, subcategoria_id=subcategoria_id)
        chicos = [(c, m) for c, m, f in items if 0 < m < 150]
        total = sum(m for _, m in chicos)
        n_meses = len(meses_plan) if meses_plan else 3
        periodo = f" en {', '.join(meses_plan)}" if meses_plan else " (últimos 3 meses)"
        cat_str = f" en {categoria}" if categoria else ""
        return (f"Gasto hormiga{cat_str}{periodo} (gastos < $150): "
                f"${total:,.0f} en {len(chicos)} gastos chiquitos. "
                f"Equivale a ${total/n_meses:,.0f} al mes en gastos pequeños.")

    # ── NUEVOS MODOS ─────────────────────────────────────────────────────────────

    if modo == "dia_mas_caro":
        # El día del mes con más gasto total
        meses_t = meses_plan or [mes_activo_str()]
        items = _gastos_recientes(len(meses_t), categoria=categoria, meses_especificos=meses_t, subcategoria_id=subcategoria_id)
        por_dia = {}
        for c, m, f in items:
            dia = f[:10] if f else None
            if dia:
                por_dia[dia] = por_dia.get(dia, 0) + m
        if not por_dia:
            cat_str = f" en {categoria}" if categoria else ""
            return f"Sin gastos para analizar{cat_str}."
        dia_max = max(por_dia, key=por_dia.get)
        top = sorted(por_dia.items(), key=lambda x: x[1], reverse=True)[:5]
        cat_str = f" en {categoria}" if categoria else ""
        detalle = ", ".join(f"{d}=${v:,.0f}" for d, v in top)
        return (f"Día con más gasto{cat_str} ({', '.join(meses_t)}): {dia_max} (${por_dia[dia_max]:,.0f}). "
                f"Top días: {detalle}.")

    if modo == "semana_mes":
        # Gasto agrupado por semana del mes (sem1=días 1-7, sem2=8-14, sem3=15-21, sem4=22+)
        meses_t = meses_plan or [mes_activo_str()]
        items = _gastos_recientes(len(meses_t), categoria=categoria, meses_especificos=meses_t, subcategoria_id=subcategoria_id)
        semanas = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        rangos = {1: "días 1-7", 2: "días 8-14", 3: "días 15-21", 4: "días 22-31"}
        for c, m, f in items:
            if not f:
                continue
            try:
                dia_num = datetime.date.fromisoformat(f[:10]).day
                s = min((dia_num - 1) // 7 + 1, 4)
                semanas[s] += m
            except (ValueError, TypeError):
                pass
        if not any(semanas.values()):
            return "Sin gastos para analizar por semana."
        mejor = max(semanas, key=semanas.get)
        cat_str = f" en {categoria}" if categoria else ""
        detalle = ", ".join(f"Sem{s} ({rangos[s]})=${v:,.0f}" for s, v in semanas.items() if v > 0)
        return (f"Gasto por semana{cat_str} ({', '.join(meses_t)}): {detalle}. "
                f"La semana con más gasto es la semana {mejor} ({rangos[mejor]}).")

    if modo == "ultima_visita":
        # Última vez que se gastó en un comercio específico
        comercio_q = normalizar(plan.get("comercio") or "")
        nombre_comercio = plan.get("comercio") or comercio_q
        if not comercio_q:
            return "Especifica a qué comercio te refieres."
        hoy_local = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        hace_un_anio = (hoy_local - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
        gastos = query_notion_db(NOTION_DATABASE_ID,
            {"property": "Fecha", "date": {"on_or_after": hace_un_anio}})
        encontrados = []
        for g in gastos:
            props = g.get("properties", {})
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            if comercio_q not in normalizar(concepto):
                continue
            monto = props.get("Monto", {}).get("number", 0) or 0
            fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
            if fecha:
                encontrados.append((concepto, monto, fecha))
        if not encontrados:
            return f"No encontré gastos en '{nombre_comercio}' en el último año."
        encontrados.sort(key=lambda x: x[2], reverse=True)
        c, m, f = encontrados[0]
        n = len(encontrados)
        total = sum(x[1] for x in encontrados)
        dias_desde = (hoy_local - datetime.date.fromisoformat(f[:10])).days
        return (f"Última visita a {c}: {f[:10]} (hace {dias_desde} días, ${m:,.0f}). "
                f"En el último año: {n} visitas, ${total:,.0f} total.")

    if modo == "tendencia":
        # Evolución mensual de una categoría/subcategoría (o total) en los últimos 6 meses
        meses_hist = list(reversed(_meses_recientes(6)))  # orden cronológico
        puntos = []
        for mes in meses_hist:
            r = ejecutar_consulta_finanzas({"meses": [mes], "categoria": categoria, "subcategoria": subcategoria})
            puntos.append((mes, r["total"]))
        while puntos and puntos[0][1] == 0:   # quitar ceros iniciales
            puntos.pop(0)
        if len(puntos) < 2:
            cat_str = f" en {subcategoria or categoria}" if (subcategoria or categoria) else ""
            return f"No hay suficientes datos para ver la tendencia{cat_str}."
        mitad = len(puntos) // 2
        prom_antes = sum(v for _, v in puntos[:mitad]) / mitad
        prom_despues = sum(v for _, v in puntos[mitad:]) / (len(puntos) - mitad)
        cambio = ((prom_despues - prom_antes) / prom_antes * 100) if prom_antes else 0
        icono = "📈" if cambio > 5 else ("📉" if cambio < -5 else "➡️")
        cat_str = f" en {subcategoria or categoria}" if (subcategoria or categoria) else ""
        detalle = ", ".join(f"{mes}=${v:,.0f}" for mes, v in puntos)
        return (f"Tendencia{cat_str}: {detalle}. "
                f"{icono} {cambio:+.1f}% vs primeros meses del período.")

    if modo == "mes_mas_caro":
        # El mes con más gasto en un año (con filtro opcional de categoría)
        hoy_local = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        anio_str = str(plan.get("anio") or hoy_local.year)
        anio_2d  = anio_str[-2:]
        orden    = ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"]
        meses_anio = [f"{m}{anio_2d}" for m in orden if f"{m}{anio_2d}" in _meses_cache]
        if not meses_anio:
            return f"No encontré meses del año {anio_str} en los registros."
        res = ejecutar_consulta_finanzas({"meses": meses_anio, "categoria": categoria, "subcategoria": subcategoria})
        if not res["por_mes"]:
            cat_str = f" en {subcategoria or categoria}" if (subcategoria or categoria) else ""
            return f"Sin gastos{cat_str} en {anio_str}."
        mejor = max(res["por_mes"], key=res["por_mes"].get)
        cat_str = f" en {subcategoria or categoria}" if (subcategoria or categoria) else ""
        detalle = ", ".join(f"{m}=${v:,.0f}" for m, v in
                            sorted(res["por_mes"].items(),
                                   key=lambda x: orden.index(x[0][:3]) if x[0][:3] in orden else 99))
        return (f"Mes con más gasto{cat_str} en {anio_str}: {mejor} (${res['por_mes'][mejor]:,.0f}). "
                f"Desglose: {detalle}.")

    if modo == "recurrentes":
        # Gastos que aparecen en 3+ de los últimos 6 meses (gastos fijos/recurrentes)
        n_meses_rec = 6
        apariciones: dict = {}
        for mes in _meses_recientes(n_meses_rec):
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                titulo = props.get("Concepto", {}).get("title", [])
                concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
                monto = props.get("Monto", {}).get("number", 0) or 0
                clave = normalizar(concepto)[:18]
                if not clave:
                    continue
                if clave not in apariciones:
                    apariciones[clave] = {"concepto": concepto, "meses": set(), "total": 0.0}
                apariciones[clave]["meses"].add(mes)
                apariciones[clave]["total"] += monto
        recurrentes = [
            (d["concepto"], len(d["meses"]), d["total"] / len(d["meses"]))
            for d in apariciones.values() if len(d["meses"]) >= 3
        ]
        recurrentes.sort(key=lambda x: x[1], reverse=True)
        if not recurrentes:
            return "No encontré gastos que se repitan en 3 o más de los últimos 6 meses."
        detalle = "; ".join(
            f"{c} ({n}/{n_meses_rec} meses, ~${p:,.0f}/mes)" for c, n, p in recurrentes[:10])
        return f"Gastos recurrentes (últimos {n_meses_rec} meses): {detalle}."

    if modo == "dias_sin_gasto":
        # Cuántos días llevas sin gastar en una categoría (o en general)
        hoy_local = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        items = _gastos_recientes(3, categoria=categoria, subcategoria_id=subcategoria_id)
        con_fecha = [(c, m, f) for c, m, f in items if f]
        if not con_fecha:
            cat_str = f" en {categoria}" if categoria else ""
            return f"No encontré gastos{cat_str} en los últimos 3 meses."
        ultimo = max(con_fecha, key=lambda x: x[2])
        fecha_ult = datetime.date.fromisoformat(ultimo[2][:10])
        dias = (hoy_local - fecha_ult).days
        cat_str = f" en {categoria}" if categoria else ""
        return (f"El último gasto{cat_str} fue el {ultimo[2][:10]} ({ultimo[0]}, ${ultimo[1]:,.0f}). "
                f"Llevas {dias} día{'s' if dias != 1 else ''} sin gastar{cat_str}.")

    if modo == "promedio_dia":
        # Gasto promedio por día en el mes activo (o en meses específicos)
        hoy_local = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        activo    = mes_activo_str()
        meses_t   = meses_plan or [activo]
        res = ejecutar_consulta_finanzas({"meses": meses_t, "categoria": categoria, "subcategoria": subcategoria})
        if res["total"] == 0:
            return "Sin gastos para calcular el promedio diario."
        if len(meses_t) == 1 and meses_t[0] == activo:
            dias = max(hoy_local.day, 1)
            nota = f"{dias} días del mes en curso"
        else:
            dias = len(meses_t) * 30
            nota = f"~{dias} días ({len(meses_t)} meses)"
        promedio = res["total"] / dias
        cat_str = f" en {categoria}" if categoria else ""
        return (f"Gasto total{cat_str} ({', '.join(meses_t)}): ${res['total']:,.0f} ({nota}). "
                f"Promedio diario: ${promedio:,.0f}/día.")

    if modo == "ranking_frecuencia":
        # Categorías ordenadas por número de transacciones (no por monto)
        meses_t = meses_plan or _meses_recientes(3)
        por_cat: dict = {}
        for mes in meses_t:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                pr = _presupuesto_de_props(props)
                if pr:
                    por_cat[pr] = por_cat.get(pr, 0) + 1
        if not por_cat:
            return "Sin datos para el ranking."
        ranking = sorted(por_cat.items(), key=lambda x: x[1], reverse=True)
        detalle = ", ".join(f"{k} ({v} compras)" for k, v in ranking[:8])
        return f"Categorías por número de compras ({', '.join(meses_t)}): {detalle}."

    if modo == "proyeccion_ahorro":
        # Si eliminaras X comercio, ¿cuánto ahorrarías al año?
        comercio_q = normalizar(plan.get("comercio") or "")
        nombre_comercio = plan.get("comercio") or comercio_q
        if not comercio_q:
            return "Especifica qué comercio o hábito quieres analizar."
        hoy_local = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        hace_un_anio = (hoy_local - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
        gastos = query_notion_db(NOTION_DATABASE_ID,
            {"property": "Fecha", "date": {"on_or_after": hace_un_anio}})
        total, conteo = 0.0, 0
        for g in gastos:
            props = g.get("properties", {})
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            if comercio_q not in normalizar(concepto):
                continue
            monto = props.get("Monto", {}).get("number", 0) or 0
            total += monto
            conteo += 1
        if conteo == 0:
            return f"No encontré gastos en '{nombre_comercio}' en el último año."
        promedio_mes = total / 12
        return (f"En el último año gastaste ${total:,.0f} en {nombre_comercio} "
                f"({conteo} visitas, ~${promedio_mes:,.0f}/mes). "
                f"Si lo eliminaras, ahorrarías ~${total:,.0f} al año.")

    if modo == "msi_tracker":
        # MSIs activos: parse "Concepto X/Total" en subcategoría MSI
        msi_id = SC.get("MSI", "").replace("-", "")
        hoy_iso = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
        gastos = query_notion_db(NOTION_DATABASE_ID, {"and": [
            {"property": "Fecha", "date": {"on_or_after": "2020-01-01"}},
            {"property": "Fecha", "date": {"on_or_before": hoy_iso}},
        ]})
        msi_map = {}
        for g in gastos:
            props = g.get("properties", {})
            rel_sc = props.get("Subcategoria", {}).get("relation", [])
            if not any(r.get("id", "").replace("-", "") == msi_id for r in rel_sc):
                continue
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            monto = props.get("Monto", {}).get("number", 0) or 0
            mm = re.search(r'^(.+?)\s+(\d{1,2})\s*/\s*(\d{1,2})\s*$', concepto)
            if not mm:
                continue
            base, actual, total = mm.group(1).strip(), int(mm.group(2)), int(mm.group(3))
            clave = normalizar(base)
            if clave not in msi_map or msi_map[clave]["actual"] < actual:
                msi_map[clave] = {"concepto": base, "actual": actual, "total": total, "monto": monto}
        if not msi_map:
            return "No encontré MSIs en los registros. Recuerda usar el formato 'Concepto X/Total' al registrarlos."
        activos = [v for v in msi_map.values() if v["actual"] < v["total"]]
        terminados = [v for v in msi_map.values() if v["actual"] >= v["total"]]
        if not activos:
            return f"Todos los MSIs registrados están terminados ({len(terminados)} en total). 🎉"
        activos.sort(key=lambda x: x["actual"] / x["total"])
        total_mensual = sum(a["monto"] for a in activos)
        partes = []
        for a in activos:
            restantes = a["total"] - a["actual"]
            partes.append(
                f"{a['concepto']}: pago {a['actual']}/{a['total']}, "
                f"quedan {restantes} × ${a['monto']:,.0f} = ${restantes * a['monto']:,.0f} restante"
            )
        return (f"MSIs activos ({len(activos)}): {'; '.join(partes)}. "
                f"Compromiso mensual en MSI: ${total_mensual:,.0f}/mes.")

    if modo == "oportunidades_ahorro":
        # Últimos 3 meses vs promedio histórico (6 meses anteriores) por categoría
        meses_rec = _meses_recientes(3)
        meses_hist_prev = _meses_recientes(9)[3:]  # 6 meses antes de los últimos 3
        def _prom_cats(meses_lista):
            acum, cnt = {}, 0
            for mes in meses_lista:
                r = ejecutar_consulta_finanzas({"meses": [mes]})
                if r["total"] > 0:
                    cnt += 1
                    for cat, val in r["por_categoria"].items():
                        acum[cat] = acum.get(cat, 0) + val
            return {k: v / cnt for k, v in acum.items()} if cnt else {}
        prom_rec  = _prom_cats(meses_rec)
        prom_hist = _prom_cats(meses_hist_prev)
        if not prom_rec or not prom_hist:
            return "No hay suficientes datos históricos para calcular oportunidades de ahorro."
        ops = []
        for cat, rec in prom_rec.items():
            hist = prom_hist.get(cat, 0)
            if hist > 200 and rec > hist * 1.10:
                exc = rec - hist
                ops.append((cat, rec, hist, exc, exc * 12))
        ops.sort(key=lambda x: x[3], reverse=True)
        if not ops:
            return "¡Buen control! No hay categorías significativamente por encima de tu promedio histórico."
        partes = [
            f"{c} ${rec:,.0f}/mes (hist. ${hist:,.0f}, exceso +${exc:,.0f} → ~${anual:,.0f}/año)"
            for c, rec, hist, exc, anual in ops[:5]
        ]
        total_pot = sum(o[4] for o in ops[:5])
        return (f"Oportunidades de ahorro (últimos 3 meses vs histórico): {'; '.join(partes)}. "
                f"Potencial total de ahorro: ~${total_pot:,.0f}/año.")

    if modo == "posicion_financiera":
        # Ingreso estimado vs gasto real del ciclo activo
        ciclo = mes_activo_str()
        ingreso = None
        for u in USUARIOS_AUTORIZADOS:
            v = cargar_meta(u, "INGRESO", ciclo)
            if v:
                ingreso = v
                break
        gasto_r = ejecutar_consulta_finanzas({"meses": [ciclo]})
        gastado = gasto_r["total"]
        if not ingreso:
            return (f"Gasto actual en {ciclo}: ${gastado:,.0f} en {gasto_r['conteo']} movimientos. "
                    f"No hay ingreso estimado declarado para este ciclo. "
                    f"Decláralo con: 'Este mes esperamos ganar $X'.")
        resto = ingreso - gastado
        pct   = (gastado / ingreso * 100) if ingreso else 0
        hoy_l = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        dias_e = max(hoy_l.day, 1)
        proj   = gastado / dias_e * 30
        ahorro_proy = ingreso - proj
        return (f"Ciclo {ciclo}: gastado ${gastado:,.0f} de ${ingreso:,.0f} estimados ({pct:.0f}%). "
                f"Saldo libre: ${resto:,.0f}. "
                f"Al ritmo actual proyectas gastar ~${proj:,.0f} este mes "
                f"→ ahorro estimado ~${ahorro_proy:,.0f}.")

    if modo == "tendencia_ingresos":
        # Ingresos declarados vs gasto por ciclo en los últimos 6 meses
        meses_hist = list(reversed(_meses_recientes(6)))
        puntos = []
        for mes in meses_hist:
            ingreso = None
            for u in USUARIOS_AUTORIZADOS:
                v = cargar_meta(u, "INGRESO", mes)
                if v:
                    ingreso = v
                    break
            gasto_r = ejecutar_consulta_finanzas({"meses": [mes]})
            if ingreso or gasto_r["total"] > 0:
                puntos.append((mes, gasto_r["total"], ingreso))
        while puntos and puntos[0][1] == 0 and not puntos[0][2]:
            puntos.pop(0)
        if not puntos:
            return "No hay datos suficientes para comparar ingresos y gastos históricos."
        partes = []
        for mes, gasto, ingreso in puntos:
            if ingreso:
                pct = (gasto / ingreso * 100)
                diff = ingreso - gasto
                partes.append(f"{mes}: gastado ${gasto:,.0f} / estimado ${ingreso:,.0f} ({pct:.0f}%, {'ahorrado' if diff >= 0 else 'excedido'} ${abs(diff):,.0f})")
            else:
                partes.append(f"{mes}: gastado ${gasto:,.0f} (sin ingreso declarado)")
        return f"Ingresos estimados vs gasto (últimos 6 ciclos): {'; '.join(partes)}."

    # ── NUEVOS MODOS v27 ─────────────────────────────────────────────────────

    if modo == "ranking_monto":
        meses_t = meses_plan or [mes_activo_str()]
        n_top = int(plan.get("n_top") or 5)
        items_raw = []
        for mes in meses_t:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                titulo = props.get("Concepto", {}).get("title", [])
                concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
                fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
                pr = _presupuesto_de_props(props)
                if categoria and pr != categoria:
                    continue
                if subcategoria_id:
                    rel_sc = props.get("Subcategoria", {}).get("relation", [])
                    if not any(r.get("id", "").replace("-", "") == subcategoria_id for r in rel_sc):
                        continue
                items_raw.append((concepto, monto, fecha, pr))
        if not items_raw:
            return "Sin gastos para mostrar."
        top = sorted(items_raw, key=lambda x: x[1], reverse=True)[:n_top]
        detalle = "; ".join(f"{c} ${m:,.0f} ({f[:10] if f else '?'})" for c, m, f, _ in top)
        cat_str = f" en {categoria}" if categoria else ""
        return f"Top {len(top)} gastos más grandes{cat_str} ({', '.join(meses_t)}): {detalle}."

    if modo == "duplicados":
        meses_t = meses_plan or [mes_activo_str()]
        items_raw = []
        for mes in meses_t:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                titulo = props.get("Concepto", {}).get("title", [])
                concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
                fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
                items_raw.append((normalizar(concepto)[:20], monto, fecha[:10] if fecha else ""))
        agrupados: dict = {}
        for c, m, f in items_raw:
            clave = (c, m)
            agrupados.setdefault(clave, []).append(f)
        dupls = [(c, m, fechas) for (c, m), fechas in agrupados.items() if len(fechas) >= 2]
        if not dupls:
            return f"No encontré posibles duplicados en {', '.join(meses_t)}. ✅"
        dupls.sort(key=lambda x: x[1], reverse=True)
        partes = [f"'{c}' ${m:,.0f} × {len(f)} veces ({', '.join(sorted(f))})"
                  for c, m, f in dupls[:8]]
        return f"Posibles duplicados en {', '.join(meses_t)}: {'; '.join(partes)}."

    if modo == "margen_presupuesto":
        ciclo = (meses_plan or [mes_activo_str()])[0]
        res = ejecutar_consulta_finanzas({"meses": [ciclo]})
        gastos_pr = res.get("por_categoria", {})
        partes = []
        for pr_name in PR.keys():
            gasto = gastos_pr.get(pr_name, 0)
            meta = None
            for u in USUARIOS_AUTORIZADOS:
                v = cargar_meta(u, pr_name, ciclo)
                if v:
                    meta = v
                    break
            if meta:
                pct = (gasto / meta * 100) if meta else 0
                falta = meta - gasto
                emoji = "🔴" if pct >= 100 else ("🟡" if pct >= 80 else "🟢")
                partes.append(f"{emoji} {pr_name}: ${gasto:,.0f}/{meta:,.0f} ({pct:.0f}%"
                              f"{', excedido' if falta < 0 else f', falta ${falta:,.0f}'})")
            elif gasto > 0:
                partes.append(f"⚪ {pr_name}: ${gasto:,.0f} (sin meta)")
        if not partes:
            return f"No hay gastos ni metas registradas en {ciclo}."
        return f"Margen por presupuesto ({ciclo}): {'; '.join(partes)}."

    if modo == "proyeccion_ciclo":
        ciclo = mes_activo_str()
        res = ejecutar_consulta_finanzas({"meses": [ciclo]})
        gastado = res["total"]
        hoy_l = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        dias_e = max(hoy_l.day, 1)
        proj = gastado / dias_e * 30
        tot = _totales_por_ciclo()
        otros = [v for k, v in tot.items() if k != ciclo and v > 0]
        resultado = (f"Ciclo {ciclo}: ${gastado:,.0f} en {dias_e} días. "
                     f"Al ritmo actual proyectas ~${proj:,.0f} al cierre.")
        if otros:
            prom_hist = sum(otros) / len(otros)
            dif = proj - prom_hist
            resultado += (f" Promedio histórico: ${prom_hist:,.0f} → proyectas "
                          f"${abs(dif):,.0f} {'más' if dif > 0 else 'menos'} que tu promedio.")
        ingreso = None
        for u in USUARIOS_AUTORIZADOS:
            v = cargar_meta(u, "INGRESO", ciclo)
            if v:
                ingreso = v
                break
        if ingreso:
            resultado += f" Con ingreso ${ingreso:,.0f}: ahorro proyectado ~${ingreso - proj:,.0f}."
        return resultado

    if modo == "fechas_futuras":
        hoy_iso = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).strftime("%Y-%m-%d")
        gastos = query_notion_db(NOTION_DATABASE_ID,
                                 {"property": "Fecha", "date": {"after": hoy_iso}})
        encontrados = []
        for g in gastos:
            props = g.get("properties", {})
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            monto = props.get("Monto", {}).get("number", 0) or 0
            fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
            encontrados.append((concepto, monto, fecha[:10] if fecha else "?"))
        if not encontrados:
            return "No encontré gastos con fechas futuras. ✅"
        partes = [f"{c} ${m:,.0f} ({f})" for c, m, f in encontrados[:10]]
        return (f"⚠️ {len(encontrados)} gasto(s) con fecha futura (posibles errores): "
                f"{'; '.join(partes)}.")

    if modo == "por_tarjeta":
        meses_t = meses_plan or [mes_activo_str()]
        por_tarjeta: dict = {}
        conteo_t: dict = {}
        for mes in meses_t:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                pago_sel = props.get("Pago", {}).get("select")
                tarjeta = (pago_sel.get("name", "") if pago_sel else "") \
                    or "".join(rt.get("plain_text", "")
                               for rt in props.get("Estado de Cuenta", {}).get("rich_text", [])) \
                    or "".join(rt.get("plain_text", "")
                               for rt in props.get("Tarjeta", {}).get("rich_text", [])) \
                    or "Sin tarjeta"
                por_tarjeta[tarjeta] = por_tarjeta.get(tarjeta, 0) + monto
                conteo_t[tarjeta] = conteo_t.get(tarjeta, 0) + 1
        if not por_tarjeta:
            return "Sin gastos para agrupar por tarjeta."
        total = sum(por_tarjeta.values())
        ranking = sorted(por_tarjeta.items(), key=lambda x: x[1], reverse=True)
        partes = [f"{t}: ${m:,.0f} ({conteo_t[t]} gastos, {m/total*100:.0f}%)" for t, m in ranking]
        return f"Gasto por tarjeta ({', '.join(meses_t)}): {'; '.join(partes)}. Total: ${total:,.0f}."

    if modo == "semana_mas_cara":
        meses_t = meses_plan or _meses_recientes(2)
        items = _gastos_recientes(len(meses_t), categoria=categoria,
                                  meses_especificos=meses_t, subcategoria_id=subcategoria_id)
        semanas: dict = {}
        for c, m, f in items:
            if not f:
                continue
            try:
                d = datetime.date.fromisoformat(f[:10])
                lunes = d - datetime.timedelta(days=d.weekday())
                semanas[lunes.isoformat()] = semanas.get(lunes.isoformat(), 0) + m
            except (ValueError, TypeError):
                pass
        if not semanas:
            return "Sin suficientes gastos para analizar por semana."
        mejor = max(semanas, key=semanas.get)
        top = sorted(semanas.items(), key=lambda x: x[1], reverse=True)[:3]
        cat_str = f" en {categoria}" if categoria else ""
        domingo = (datetime.date.fromisoformat(mejor) + datetime.timedelta(days=6)).isoformat()
        detalle = "; ".join(f"sem {l}: ${v:,.0f}" for l, v in top)
        return (f"Semana más cara{cat_str} ({', '.join(meses_t)}): {mejor} al {domingo} "
                f"(${semanas[mejor]:,.0f}). Top semanas: {detalle}.")

    if modo == "comparar_ciclos":
        meses_t = meses_plan or [mes_activo_str()]
        if len(meses_t) < 2:
            meses_t = [meses_t[0], _mes_anterior(meses_t[0])]
        m1, m2 = meses_t[0], meses_t[1]
        r1 = ejecutar_consulta_finanzas({"meses": [m1], "categoria": categoria,
                                         "subcategoria": subcategoria})
        r2 = ejecutar_consulta_finanzas({"meses": [m2], "categoria": categoria,
                                         "subcategoria": subcategoria})
        dif = r1["total"] - r2["total"]
        pct = (dif / r2["total"] * 100) if r2["total"] else 0
        cat_str = f" en {subcategoria or categoria}" if (subcategoria or categoria) else ""
        icono = "📈" if dif > 0 else "📉"
        resultado = (f"Comparación{cat_str}: {m1} ${r1['total']:,.0f} vs {m2} ${r2['total']:,.0f}. "
                     f"{icono} {m1} tiene ${abs(dif):,.0f} {'más' if dif > 0 else 'menos'} ({pct:+.1f}%).")
        if not (categoria or subcategoria) and r1["por_categoria"] and r2["por_categoria"]:
            todas = set(r1["por_categoria"]) | set(r2["por_categoria"])
            diffs = [(cat, r1["por_categoria"].get(cat, 0), r2["por_categoria"].get(cat, 0))
                     for cat in todas]
            diffs = [(c, v1, v2, v1 - v2) for c, v1, v2 in diffs if abs(v1 - v2) > 200]
            if diffs:
                diffs.sort(key=lambda x: abs(x[3]), reverse=True)
                comp = "; ".join(f"{c} {'+' if d > 0 else ''}{d:,.0f}"
                                 for c, _, _, d in diffs[:5])
                resultado += f" Diferencias: {comp}."
        return resultado

    return None

def _es_finde(fecha_iso: str):
    """True si la fecha cae en sábado o domingo; False entre semana; None si no parsea."""
    try:
        return datetime.date.fromisoformat(fecha_iso[:10]).weekday() >= 5
    except (ValueError, TypeError):
        return None

# ── ACCIONES MASIVAS ─────────────────────────────────────────────────────────

def _accion_preview(payload: dict) -> tuple:
    """
    Busca gastos afectados por la acción masiva pedida.
    Retorna (texto_preview: str, gastos: list).
    gastos vacío = no encontró nada → mostrar preview como mensaje final.
    """
    operacion          = payload.get("operacion", "")
    filtro_concepto    = normalizar(payload.get("filtro_concepto") or "")
    filtro_subcatname  = (payload.get("filtro_subcategoria") or "").strip()
    filtro_tarjeta     = (payload.get("filtro_tarjeta") or "").upper()
    filtro_monto_max   = payload.get("filtro_monto_max")
    meses_p            = [m.upper() for m in (payload.get("meses") or [])] or [mes_activo_str()]
    nueva_subcatname   = payload.get("nueva_subcategoria") or ""
    nuevo_presup       = payload.get("nuevo_presupuesto") or ""
    nuevo_concepto     = payload.get("nuevo_concepto") or ""
    nueva_tarjeta      = (payload.get("nueva_tarjeta") or "").upper()

    filtro_sc_id = SC.get(filtro_subcatname, "").replace("-", "") if filtro_subcatname else None
    gastos_enc = []

    if operacion == "sin_categoria":
        for mes in meses_p:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                if props.get("Subcategoria", {}).get("relation"):
                    continue
                titulo = props.get("Concepto", {}).get("title", [])
                concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
                monto = props.get("Monto", {}).get("number", 0) or 0
                fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
                gastos_enc.append({"id": g["id"], "concepto": concepto, "monto": monto,
                                   "fecha": fecha[:10] if fecha else ""})
    elif operacion == "crear_meta_auto":
        ciclo = meses_p[0]
        res = ejecutar_consulta_finanzas({"meses": [ciclo]})
        pr_top = max(res["por_categoria"].items(), key=lambda x: x[1], default=(None, 0))
        if not pr_top[0]:
            return f"No encontré gastos en {ciclo} para sugerir una meta.", []
        pr_name, pr_total = pr_top
        meta_actual = None
        for u in USUARIOS_AUTORIZADOS:
            v = cargar_meta(u, pr_name, ciclo)
            if v:
                meta_actual = v
                break
        sugerencia = round(pr_total * 1.1 / 100) * 100  # +10% redondeado a 100
        preview = (f"📊 La categoría con más gasto en {ciclo} es *{pr_name}* (${pr_total:,.0f}).\n\n"
                   f"{'Meta actual: $' + f'{meta_actual:,.0f}' + chr(10) + chr(10) if meta_actual else ''}"
                   f"¿Crear meta para *{pr_name}* en ${sugerencia:,.0f}?")
        gastos_enc.append({"id": "_meta_", "concepto": pr_name, "monto": sugerencia,
                           "fecha": ciclo, "_presupuesto": pr_name, "_ciclo": ciclo})
        return preview, gastos_enc
    elif operacion == "cierre_ciclo":
        ciclo = meses_p[0]
        mid = buscar_mes_id(ciclo)
        if not mid:
            return f"No encontré el ciclo {ciclo}.", []
        for g in query_notion_db(NOTION_DATABASE_ID,
                                 {"property": "Mes", "relation": {"contains": mid}}):
            props = g.get("properties", {})
            titulo = props.get("Concepto", {}).get("title", [])
            concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
            monto = props.get("Monto", {}).get("number", 0) or 0
            fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
            gastos_enc.append({"id": g["id"], "concepto": concepto, "monto": monto,
                               "fecha": fecha[:10] if fecha else ""})
    else:
        for mes in meses_p:
            mid = buscar_mes_id(mes)
            if not mid:
                continue
            for g in query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Mes", "relation": {"contains": mid}}):
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                titulo = props.get("Concepto", {}).get("title", [])
                concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
                fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
                tarjeta = _leer_tarjeta(props)
                if filtro_concepto and filtro_concepto not in normalizar(concepto):
                    continue
                if filtro_sc_id:
                    rel_sc = props.get("Subcategoria", {}).get("relation", [])
                    if not any(r.get("id", "").replace("-", "") == filtro_sc_id for r in rel_sc):
                        continue
                if filtro_tarjeta and filtro_tarjeta not in tarjeta.upper():
                    continue
                if filtro_monto_max is not None and monto > filtro_monto_max:
                    continue
                gastos_enc.append({"id": g["id"], "concepto": concepto, "monto": monto,
                                   "fecha": fecha[:10] if fecha else "", "tarjeta": tarjeta})

    if not gastos_enc:
        return f"No encontré gastos que coincidan con el criterio en {', '.join(meses_p)}.", []

    n = len(gastos_enc)
    muestra = gastos_enc[:5]
    lineas = "\n".join(f"• {g['concepto']} ${g['monto']:,.0f} ({g['fecha']})" for g in muestra)
    if n > 5:
        lineas += f"\n  … y {n - 5} más"

    if operacion == "reclasificar":
        accion_txt = f"Cambiar subcategoría → *{nueva_subcatname}*" + (
            f" / presupuesto → *{nuevo_presup}*" if nuevo_presup else "")
    elif operacion == "renombrar":
        accion_txt = f"Renombrar concepto → *{nuevo_concepto}*"
    elif operacion == "cambiar_tarjeta":
        accion_txt = f"Cambiar tarjeta → *{nueva_tarjeta}*"
    elif operacion in ("borrar_chicos", "borrar"):
        accion_txt = "⚠️ Archivar (eliminar) estos gastos"
    elif operacion == "sin_categoria":
        accion_txt = "Solo mostrar (sin modificar)"
    elif operacion == "cierre_ciclo":
        total_c = sum(g["monto"] for g in gastos_enc)
        accion_txt = f"⚠️ Archivar {n} gastos del ciclo {meses_p[0]} (total ${total_c:,.0f})"
    else:
        accion_txt = operacion

    preview = (f"🔍 Encontré *{n} gasto(s)*:\n{lineas}\n\n"
               f"Acción: {accion_txt}\n\n"
               f"¿Confirmas?")
    return preview, gastos_enc


def _accion_ejecutar(payload: dict, gastos: list) -> str:
    """Aplica la acción masiva. Retorna el mensaje de resultado."""
    operacion        = payload.get("operacion", "")
    nueva_subcatname = payload.get("nueva_subcategoria") or ""
    nuevo_presup     = payload.get("nuevo_presupuesto") or ""
    nuevo_concepto   = payload.get("nuevo_concepto") or ""
    nueva_tarjeta    = (payload.get("nueva_tarjeta") or "").upper()
    meses_p          = [m.upper() for m in (payload.get("meses") or [])] or [mes_activo_str()]

    if operacion == "sin_categoria":
        return f"📋 {len(gastos)} gasto(s) sin subcategoría listados arriba."

    if operacion == "crear_meta_auto":
        g0 = gastos[0]
        pr_name = g0["_presupuesto"]
        ciclo = g0["_ciclo"]
        sugerencia = g0["monto"]
        uid0 = next(iter(USUARIOS_AUTORIZADOS))
        ok = guardar_meta(uid0, pr_name, sugerencia, ciclo)
        return (f"🎯 Meta creada: *{pr_name}* ≤ ${sugerencia:,.0f} en {ciclo}." if ok
                else "❌ No pude guardar la meta.")

    n_ok, n_err = 0, 0
    for g in gastos:
        page_id = g["id"]
        props_upd = {}
        try:
            if operacion == "reclasificar":
                if nueva_subcatname:
                    sid = SC.get(nueva_subcatname)
                    if sid:
                        props_upd["Subcategoria"] = {"relation": [{"id": sid}]}
                if nuevo_presup or nueva_subcatname:
                    pr_name = nuevo_presup or SUBCAT_PRESUPUESTO.get(nueva_subcatname, "")
                    pid = PR.get(pr_name)
                    if pid:
                        props_upd["Presupuesto"] = {"relation": [{"id": pid}]}
            elif operacion == "renombrar" and nuevo_concepto:
                props_upd["Concepto"] = {"title": [{"text": {"content": nuevo_concepto}}]}
            elif operacion == "cambiar_tarjeta" and nueva_tarjeta:
                props_upd["Tarjeta"] = {"rich_text": [{"text": {"content": nueva_tarjeta}}]}
                props_upd["Pago"]    = {"select": {"name": nueva_tarjeta}}
            elif operacion in ("borrar_chicos", "borrar", "cierre_ciclo"):
                r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{page_id}",
                                   headers=nh(), json={"archived": True},
                                   timeout=NOTION_T_DEFAULT)
                if r and r.status_code == 200:
                    n_ok += 1
                else:
                    n_err += 1
                continue

            if props_upd:
                r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{page_id}",
                                   headers=nh(), json={"properties": props_upd},
                                   timeout=NOTION_T_DEFAULT)
                if r and r.status_code == 200:
                    n_ok += 1
                else:
                    n_err += 1
        except Exception as ex:
            logger.error(f"accion_ejecutar error page {page_id}: {ex}")
            n_err += 1

    if n_err == 0:
        return f"✅ {n_ok} gasto(s) actualizados correctamente."
    return f"⚠️ {n_ok} actualizados, {n_err} con error."


async def callback_accion(update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if query.data == "accion_cancelar":
        context.user_data.pop("accion_pendiente", None)
        await query.message.edit_text("❌ Acción cancelada.")
        return
    pendiente = context.user_data.pop("accion_pendiente", None)
    if not pendiente:
        await query.message.edit_text("⚠️ El bot se reinició y perdió el contexto. Repite la acción.")
        return
    await query.message.edit_text("⏳ Aplicando cambios en Notion…")
    resultado = await asyncio.to_thread(_accion_ejecutar, pendiente["payload"], pendiente["gastos"])
    await query.message.edit_text(resultado, parse_mode="Markdown")


async def responder_consulta_groq(texto: str, user_id: int, update, context) -> bool:
    """
    Responde una consulta en lenguaje natural con datos reales de Notion, en 2 pasos:
      1) Groq genera un plan de consulta (JSON con filtros).
      2) ejecutar_consulta_finanzas() trae los datos de forma determinística.
      3) Groq redacta la respuesta a partir de esos datos.
    Retorna True si respondió, False si no aplica (cae al flujo normal).
    """
    if not GROQ_API_KEY:
        return False

    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    activo = mes_activo_str()
    meses_disp = ", ".join(sorted(_meses_cache.keys())) or activo
    categorias   = ", ".join(PR.keys())
    subcategorias = ", ".join(SC.keys())

    ayer      = (hoy - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    hoy_iso   = hoy.strftime("%Y-%m-%d")
    # Lunes y domingo de la semana pasada
    lunes_pasado  = hoy - datetime.timedelta(days=hoy.weekday() + 7)
    domingo_pasado = lunes_pasado + datetime.timedelta(days=6)
    # Lunes de esta semana
    lunes_esta    = hoy - datetime.timedelta(days=hoy.weekday())

    hist = obtener_historial(user_id)
    bloque_hist = ""
    if hist:
        ctx = "\n".join(f"{m['role']}: {m['content']}" for m in hist[-4:])
        bloque_hist = (f"\nContexto reciente de la conversación (úsalo para resolver referencias como "
                       f"\"¿y ayer?\", \"¿y en esa categoría?\", \"¿y la semana pasada?\"):\n{ctx}\n")
    # Filtros del plan anterior — permite carryover de categoria/subcategoria/tarjeta
    last_q = _mem_init(user_id).get("last_query", {})
    if last_q:
        filtros_prev = {k: v for k, v in last_q.items()
                        if k not in ("modo", "historico", "meses", "anio") and v}
        if filtros_prev:
            bloque_hist += (f"Filtros activos de la consulta anterior (reutiliza los que apliquen "
                            f"si el usuario dice 'lo mismo', 'en esa subcategoría', etc.): "
                            f"{json.dumps(filtros_prev, ensure_ascii=False)}\n")

    prompt_plan = f"""Hoy es {hoy.strftime('%d/%m/%Y')} ({hoy_iso}). Mes de ciclo activo: {activo}.
Meses disponibles: {meses_disp}
Categorías de presupuesto válidas: {categorias}
Subcategorías válidas: {subcategorias}

Fechas de referencia:
- Ayer: {ayer}  | Esta semana (lunes): {lunes_esta.strftime('%Y-%m-%d')}
- Semana pasada: {lunes_pasado.strftime('%Y-%m-%d')} a {domingo_pasado.strftime('%Y-%m-%d')}
- Hace 7 días: {(hoy - datetime.timedelta(days=6)).strftime('%Y-%m-%d')}
{bloque_hist}
El usuario pregunta: "{texto}"

Devuelve SOLO JSON válido:
{{
  "modo": "detalle",
  "meses": ["{activo}"],
  "categoria": null,
  "subcategoria": null,
  "tarjeta": null,
  "comercio": null,
  "fecha_desde": null,
  "fecha_hasta": null,
  "anio": null,
  "historico": false
}}

MODOS disponibles:
- "detalle": totales por meses o rango de fechas. Para "¿cuántas veces fui a X?" usa comercio.
- "por_anio": gasto por año ("¿qué año gasté más?").
- "primero"/"ultimo"/"mayor": gasto más antiguo/reciente/caro de la historia. "ultimo" es SOLO para "el último gasto que hice" (sin mencionar ningún comercio ni categoría). NUNCA usar "ultimo" cuando el usuario menciona un comercio específico — en ese caso usar "ultima_visita" con comercio.
- "ranking_categorias": top categorías por monto ("¿en qué gasto más?").
- "ranking_frecuencia": top categorías por número de compras ("¿dónde compro más seguido?", "¿qué categoría tiene más transacciones?").
- "promedio_mensual": promedio de gasto por mes. Acepta "categoria".
- "promedio_dia": cuánto gasto al día en promedio. Acepta "categoria" y "meses".
- "dia_semana": entre semana vs fin de semana. Acepta "categoria" y "meses".
- "dia_mas_caro": el día del mes con más gasto. Acepta "categoria" y "meses".
- "semana_mes": gasto por semana del mes (sem1=días1-7, sem2=8-14...). Acepta "categoria" y "meses".
- "desviacion": este mes vs promedio histórico. Acepta "categoria".
- "tendencia": si el gasto sube o baja en los últimos 6 meses. Acepta "categoria".
- "mes_mas_caro": qué mes fue el más caro de un año. Usa "anio" (ej "2025") y opcionalmente "categoria".
- "hormiga": gastos pequeños (<$150). Acepta "categoria" y "meses".
- "recurrentes": gastos que se repiten cada mes ("¿cuáles son mis gastos fijos?").
- "dias_sin_gasto": días desde el último gasto en una categoría. Requiere "categoria".
- "ultima_visita": última vez que gasté en un comercio o lugar específico. Requiere "comercio". Usar cuando el usuario pregunta "¿cuál fue mi último gasto de X?", "¿cuándo fui por última vez a X?", "¿cuándo fue la última vez que compré en X?". Ej: "último gasto de autolavado" → ultima_visita + comercio:"autolavado".
- "proyeccion_ahorro": cuánto ahorraría si dejara un hábito. Requiere "comercio".
- "msi_tracker": cuántos meses sin intereses tengo activos, cuánto debo en total, cuándo terminan.
- "oportunidades_ahorro": dónde puedo ahorrar, en qué categorías gasto de más vs mi historial.
- "posicion_financiera": cuánto he gastado vs mi ingreso estimado del ciclo, cuánto me queda, proyección de ahorro del mes.
- "tendencia_ingresos": ingresos estimados vs gasto real en los últimos 6 ciclos.
- "ranking_monto": top gastos más caros del período. Acepta "categoria", "subcategoria", "meses". Usa "n_top" (número, default 5).
- "duplicados": posibles gastos duplicados (mismo concepto y monto más de una vez). Acepta "meses".
- "margen_presupuesto": cuánto falta para el límite de cada presupuesto en el ciclo. Acepta "meses" (1 ciclo).
- "proyeccion_ciclo": extrapolación del gasto actual hasta fin de mes, compara con histórico.
- "fechas_futuras": gastos registrados con fecha mayor a hoy (posibles errores).
- "por_tarjeta": gasto total agrupado por tarjeta. Acepta "meses".
- "semana_mas_cara": semana de 7 días con más gasto. Acepta "categoria", "meses".
- "comparar_ciclos": comparación entre dos ciclos específicos. Usa "meses" con 2 elementos; sin especificar usa ciclo activo vs anterior.

CAMPOS:
- "fecha_desde"/"fecha_hasta" (YYYY-MM-DD): para días o rangos exactos (ayer, esta semana, el 15 mayo). Cuando se usan, "meses" se ignora.
- "meses": códigos MES+AA. "este mes"={activo}. "mes pasado"=anterior al activo. Para MES COMPLETO, no uses fecha_desde/hasta.
- "anio": año de 4 dígitos (ej "2025"), para modo mes_mas_caro u otras preguntas anuales.
- "categoria": nombre EXACTO de la lista de presupuesto (Despensa, Automovil, Servicios…), o null. Para filtrar por bolsa de presupuesto global.
- "subcategoria": nombre EXACTO de la lista de subcategorías (Abarrotes, Gasolina, Super, Treat…), o null. Úsalo cuando el usuario pregunte por un tipo de gasto específico (ej. "abarrotes", "gasolina", "super", "treat"). NOTA CRÍTICA: "Restaurantes" es tanto subcategoría como categoría de presupuesto — en caso de duda usa subcategoria=Restaurantes (más preciso). NUNCA pongas subcategoria y categoria simultáneamente.
- "tarjeta": BBVA05, BBVA12, HEYB25, BMEX04 o EFVO; solo si el usuario la menciona explícitamente. null si no especifica tarjeta.
- "comercio": texto a buscar en el concepto del gasto (ej "starbucks", "walmart"), o null.
- "historico": true cuando la pregunta sea sobre toda la historia: "en total", "desde siempre", "cuánto llevo pagado", "cuánto he gastado en total", pagos de coche (VW Polo, mensualidades), gastos recurrentes de largo plazo. Con historico=true se consultan TODOS los registros desde 2020; "meses" se ignora.
- Si la pregunta NO es sobre finanzas/gastos → {{"error":"no_finanzas"}}."""

    raw = await asyncio.to_thread(groq_completar, prompt_plan, 220)
    plan = _extraer_json(raw)
    if not plan:
        logger.warning(f"Plan de consulta inválido — raw: {(raw or '')[:120]}")
        return False
    if plan.get("error") == "no_finanzas":
        return False

    # Aviso previo para consultas históricas (pueden tardar 15-30 s)
    if plan.get("historico"):
        await update.message.reply_text("🔍 Buscando en toda la historia, dame un momento…")

    modo = (plan.get("modo") or "detalle").strip().lower()
    res = {"conteo": 0, "total": 0.0, "meses": []}  # fallback por si no se asigna abajo
    if modo != "detalle":
        datos = await asyncio.to_thread(_datos_consulta_especial, modo, plan)
        if not datos:
            res = await asyncio.to_thread(ejecutar_consulta_finanzas, plan)
            datos = _formatear_datos_consulta(res)
    else:
        res = await asyncio.to_thread(ejecutar_consulta_finanzas, plan)
        datos = _formatear_datos_consulta(res)

    prompt_resp = f"""Eres el asistente del bot de gastos de Jordi y Nani. Responde en español mexicano, claro y directo. Usa $ con separador de miles. Emojis con moderación.

Pregunta del usuario: "{texto}"

Datos reales consultados en Notion ahora mismo:
{datos}

REGLAS DE FORMATO:
- Si los datos contienen una lista de gastos individuales (varios conceptos con monto y fecha), respóndela como bullet list: • Concepto $monto · Fecha. Luego una línea de total o resumen al final.
- Si los datos son un agregado o resumen (una sola cifra, ranking de categorías, comparativa), responde en 2-3 oraciones fluidas, sin bullets.
- Nunca mezcles ambos estilos en la misma respuesta.

REGLA CRÍTICA: responde ÚNICAMENTE con los datos mostrados arriba. PROHIBIDO usar información de mensajes anteriores, inventar cifras o mencionar meses/gastos que no aparezcan en esos datos. Si los datos dicen "Sin gastos que coincidan", dilo tal cual — no menciones otros meses ni datos de turnos previos."""

    respuesta = await asyncio.to_thread(groq_completar, prompt_resp, 400)
    if respuesta:
        mem_add_turn(user_id, "u", texto)
        mem_add_turn(user_id, "b", respuesta)
        # Guardar gastos_raw del query para referencias futuras ("dame el link", "el más caro")
        if res.get("gastos_raw"):
            mem_set_results(user_id, res["gastos_raw"], plan)
        asyncio.create_task(mem_guardar(user_id))
        await update.message.reply_text(respuesta)
        return True
    # Fallback: si el segundo LLM falla pero sí hubo datos, responde lo básico
    if res["conteo"]:
        if res.get("gastos_raw"):
            mem_set_results(user_id, res["gastos_raw"], plan)
        await update.message.reply_text(f"💰 Total: ${res['total']:,.0f} en {res['conteo']} gastos ({', '.join(res['meses'])})")
        return True
    return False

HORMIGA_SUBCATS = ("Treat", "Abarrotes", "Restaurantes", "Gasolina")

async def verificar_hormiga(gasto: dict, uid: int, context) -> None:
    """Alerta de gasto hormiga: gasto pequeño (<$150) en subcategoría de consumo frecuente
    cuando ya van 3+ en la misma subcategoría esta semana. Background, solo al que registró."""
    if (gasto.get("monto") or 0) >= 150:
        return
    subcategoria = gasto.get("subcategoria")
    if subcategoria not in HORMIGA_SUBCATS:
        return
    sc_id = SC.get(subcategoria)
    if not sc_id:
        return
    try:
        hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
        desde = (hoy - datetime.timedelta(days=7)).isoformat()
        def _contar():
            gastos = query_notion_db(NOTION_DATABASE_ID,
                                     {"property": "Fecha", "date": {"on_or_after": desde}})
            n, total = 0, 0.0
            for g in gastos:
                props = g.get("properties", {})
                rel_sc = props.get("Subcategoria", {}).get("relation", [])
                if rel_sc and rel_sc[0].get("id", "").replace("-", "") == sc_id:
                    n += 1
                    total += props.get("Monto", {}).get("number", 0) or 0
            return n, total
        n, total = await asyncio.to_thread(_contar)
        if n >= 3:
            await context.bot.send_message(
                chat_id=uid,
                text=f"☕ Llevas {n} gastos en {subcategoria} esta semana (${total:,.0f} en total).")
    except Exception as e:
        logger.warning(f"verificar_hormiga error: {e}")

async def detectar_anomalia(gasto: dict, uid: int, context) -> None:
    """Avisa si un gasto es inusualmente alto vs el historial del MISMO concepto.
    Matemática pura (sin Groq). Background, solo al que registró. Tarea 9."""
    concepto = gasto.get("concepto", "")
    monto = gasto.get("monto", 0) or 0
    if not concepto or monto <= 0:
        return
    try:
        objetivo = normalizar(concepto)
        def _montos():
            r = notion_request("POST", f"{NOTION_API_BASE}/databases/{NOTION_DATABASE_ID}/query",
                headers=nh(), json={
                    "filter": {"property": "Concepto", "title": {"contains": concepto}},
                    "sorts": [{"property": "Fecha", "direction": "descending"}],
                    "page_size": 20,
                }, timeout=NOTION_T_DEFAULT)
            out = []
            if r and r.status_code == 200:
                for g in r.json().get("results", []):
                    props = g.get("properties", {})
                    t = props.get("Concepto", {}).get("title", [])
                    c = t[0].get("text", {}).get("content", "") if t else ""
                    if normalizar(c) == objetivo:
                        m = props.get("Monto", {}).get("number", 0) or 0
                        if m > 0:
                            out.append(m)
            return out
        montos = await asyncio.to_thread(_montos)
        if monto in montos:          # quita una ocurrencia del gasto recién registrado
            montos.remove(monto)
        if len(montos) < 5:
            return
        import statistics
        media = statistics.mean(montos)
        std = statistics.pstdev(montos)
        umbral = max(2.5 * media, media + 2 * std)   # el más estricto, evita falsos positivos
        if monto > umbral:
            await context.bot.send_message(
                chat_id=uid,
                text=f"⚠️ {concepto} por ${monto:,.0f} parece inusual (tu promedio es ${media:,.0f}).")
    except Exception as e:
        logger.warning(f"detectar_anomalia error: {e}")

async def verificar_metas(gasto: dict, uid: int, context) -> None:
    """Revisa si el nuevo gasto cruza el 80% o 100% de alguna meta del ciclo. Solo avisa al cruzar."""
    try:
        ciclo = gasto.get("mes", "")
        if not ciclo:
            return
        metas = await asyncio.to_thread(cargar_metas_ciclo, uid, ciclo)
        if not metas:
            return
        mid = await asyncio.to_thread(buscar_mes_id, ciclo)
        if not mid:
            return
        gastos_mes = await asyncio.to_thread(query_notion_db, NOTION_DATABASE_ID,
                                             {"property": "Mes", "relation": {"contains": mid}})
        for meta in metas:
            presupuesto = meta.get("presupuesto", "")
            limite      = float(meta.get("limite") or 0)
            if not presupuesto or not limite:
                continue
            total = 0.0
            for g in gastos_mes:
                props = g.get("properties", {})
                monto = props.get("Monto", {}).get("number", 0) or 0
                if presupuesto == "TOTAL":
                    total += monto
                else:
                    rel_pre = props.get("Presupuesto", {}).get("relation", [])
                    if rel_pre:
                        pr_id    = rel_pre[0].get("id", "").replace("-", "")
                        pr_nom   = next((k for k, v in PR.items() if v == pr_id), None)
                        if pr_nom == presupuesto:
                            total += monto
            prev_total = max(0.0, total - gasto.get("monto", 0))
            pct        = (total      / limite) * 100
            prev_pct   = (prev_total / limite) * 100
            label = "total del ciclo" if presupuesto == "TOTAL" else presupuesto
            if pct >= 100 and prev_pct < 100:
                await context.bot.send_message(chat_id=uid,
                    text=f"🚨 *Meta alcanzada:* {label}\n${total:,.0f} de ${limite:,.0f} ({pct:.0f}%)",
                    parse_mode="Markdown")
            elif pct >= 80 and prev_pct < 80:
                restante = limite - total
                await context.bot.send_message(chat_id=uid,
                    text=f"⚠️ *80% de meta:* {label}\n${total:,.0f} de ${limite:,.0f} — quedan ${restante:,.0f}",
                    parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"verificar_metas error: {e}")

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
        mid = await asyncio.to_thread(buscar_mes_id, mes_actual)
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
    cuerpo={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props}
    r=notion_request("POST",f"{NOTION_API_BASE}/pages",headers=nh(),
        json=cuerpo,timeout=NOTION_T_DEFAULT)
    if not (r and r.status_code==200):
        return False, "", (r.text if r else "Sin respuesta")
    return True, r.json().get("id",""), ""

def _bloques_productos(productos):
    """Convierte una lista de productos [{nombre, precio}] en una tabla de Notion (Producto | Precio)."""
    if not productos:
        return None
    # Fila de encabezado
    filas = [{
        "object": "block", "type": "table_row",
        "table_row": {"cells": [
            [{"type": "text", "text": {"content": "Producto"}, "annotations": {"bold": True}}],
            [{"type": "text", "text": {"content": "Precio"},   "annotations": {"bold": True}}],
        ]},
    }]
    for p in productos[:95]:
        nombre = p.get("nombre", "").strip()
        if not nombre:
            continue
        precio = p.get("precio")
        precio_str = f"${precio:,.2f}" if isinstance(precio, (int, float)) else "—"
        filas.append({
            "object": "block", "type": "table_row",
            "table_row": {"cells": [
                [{"type": "text", "text": {"content": nombre[:200]}}],
                [{"type": "text", "text": {"content": precio_str}}],
            ]},
        })
    if len(filas) <= 1:   # solo encabezado, sin productos válidos
        return None
    return [{
        "object": "block", "type": "table",
        "table": {"table_width": 2, "has_column_header": True, "has_row_header": False, "children": filas},
    }]

# ── MENSAJES ─────────────────────────────────────────────────────────────────

def msg_gasto(g, nombre=None, notion_id=None, header=None):
    enc = header or (f"🔔 Nuevo gasto de {nombre}" if nombre else "✅ Gasto guardado")
    msg = (
        f"{enc}\n\n"
        f"📌 {_esc_md(g['concepto'])}\n"
        f"💵 ${g['monto']:,.2f}\n"
        f"🗓️ {_fecha_compacta(g['fecha'])}\n"
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
    ok, nid, err = await asyncio.to_thread(guardar_notion, gasto)
    if not ok:
        logger.error(f"Error guardando en Notion: {err}")
        await _responder(update, context, "❌ Error al guardar en Notion. Intenta de nuevo.", reply_markup=ReplyKeyboardRemove())
        return
    gasto_completo = {**gasto, "notion_id": nid}
    uid = update.effective_user.id
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
    guardar_contexto(uid, gasto_completo)  # actualiza _ultimo_gasto_usuario + mem_set_gasto
    asyncio.create_task(mem_guardar(uid))  # persiste a Notion en background
    asyncio.create_task(generar_insight_groq(gasto_completo, uid, context))
    asyncio.create_task(verificar_hormiga(gasto_completo, uid, context))
    asyncio.create_task(detectar_anomalia(gasto_completo, uid, context))
    asyncio.create_task(verificar_metas(gasto_completo, uid, context))
    import random
    if random.randint(1,50)==1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()
    await _responder(update, context,
        msg_gasto(gasto, notion_id=nid),
        reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown"
    )
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    await notificar_pareja(context, uid,
        msg_gasto(gasto, nombre=nombre, notion_id=nid),
        parse_mode="Markdown"
    )

# ── EDICIÓN CONTEXTUAL ("cámbialo a 400", "ponlo en restaurantes") ─────────────
async def _responder(update, context, text, **kw):
    """Responde al usuario funcione el update por mensaje (reply) o por callback (sin message)."""
    if getattr(update, "message", None):
        await update.message.reply_text(text, **kw)
    else:
        await context.bot.send_message(update.effective_chat.id, text, **kw)

async def notificar_pareja(context, uid, texto, **kw):
    """Envía una notificación al otro usuario (cónyuge), si está configurado. Helper único."""
    notif = USUARIOS_NOTIFICAR.get(uid)
    if notif:
        await context.bot.send_message(chat_id=notif, text=texto, **kw)

async def aplicar_edicion_contextual(update, context, campos: dict, base: dict):
    uid = update.effective_user.id
    nid = base.get("notion_id")
    if not nid:
        await _responder(update, context, "🤔 No tengo un gasto reciente para editar. Usa /corregir.")
        return
    ok, g, props, err = await asyncio.to_thread(_aplicar_edicion_notion, base, campos)
    if err == "sin_cambios":
        await _responder(update, context, "🤔 No entendí qué cambiar del último gasto.")
        return
    if not ok:
        await _responder(update, context, "❌ No pude actualizar el gasto en Notion.")
        return

    g["seguro"] = True
    guardar_contexto(uid, g)
    if _edicion_cambio_categoria(props):
        await asyncio.to_thread(guardar_aprendizaje, g["concepto"].lower(), g["subcategoria"], g["presupuesto"])
    await _responder(update, context,
        msg_gasto(g, notion_id=nid, header="✏️ Gasto actualizado"),
        reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    await notificar_pareja(context, uid,
        msg_gasto(g, notion_id=nid, header=f"✏️ {nombre} editó un gasto"),
        parse_mode="Markdown")

# ── EDICIÓN CON CONFIRMACIÓN (staging area) ──────────────────────────────────

def _construir_props_edicion(base: dict, g: dict) -> dict:
    """Construye el dict de propiedades Notion para PATCH, basado en diff base→g."""
    props = {}
    if g.get("monto") != base.get("monto"):
        props["Monto"] = {"number": g["monto"]}
    if g.get("concepto") != base.get("concepto"):
        props["Concepto"] = {"title": [{"text": {"content": g["concepto"]}}]}
    tarjeta_cambio = g.get("tarjeta") != base.get("tarjeta")
    fecha_cambio   = g.get("fecha")   != base.get("fecha")
    if tarjeta_cambio:
        props["Estado de Cuenta"] = {"rich_text": [{"text": {"content": g["tarjeta"]}}]}
        props["Pago"] = {"select": {"name": g["tarjeta"]}}
    if fecha_cambio:
        props["Fecha"] = {"date": {"start": g["fecha"]}}
    if tarjeta_cambio or fecha_cambio:
        mid = buscar_mes_id(g["mes"])
        if mid:
            props["Mes"] = {"relation": [{"id": mid}]}
    if g.get("presupuesto") != base.get("presupuesto") and g.get("presupuesto") in PR:
        props["Presupuesto"] = {"relation": [{"id": PR[g["presupuesto"]]}]}
    if g.get("subcategoria") != base.get("subcategoria") and g.get("subcategoria") in SC:
        props["Subcategoria"] = {"relation": [{"id": SC[g["subcategoria"]]}]}
    return props

def _edicion_cambio_categoria(props: dict) -> bool:
    return "Subcategoria" in props or "Presupuesto" in props

def _aplicar_edicion_notion(base: dict, campos: dict):
    """Aplica una edición real a Notion desde base+campos. Devuelve (ok, gasto, props, error)."""
    nid = base.get("notion_id")
    if not nid:
        return False, dict(base), {}, "sin_notion_id"
    g = _editar_gasto_local(base, campos)
    props = _construir_props_edicion(base, g)
    if not props:
        return False, g, props, "sin_cambios"
    r = notion_request("PATCH", f"{NOTION_API_BASE}/pages/{nid}",
                       headers=nh(), json={"properties": props}, timeout=NOTION_T_DEFAULT)
    if not (r and r.status_code == 200):
        return False, g, props, "notion_error"
    return True, g, props, ""

async def callback_edicion(update, context):
    """Maneja los botones inline de confirmación de edición (Confirmar / Cancelar)."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    staged = _staged_edits.get(uid)
    if not staged:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ No hay edición pendiente.")
        return

    if query.data == "edicion_cancel":
        _staged_edits.pop(uid, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Edición cancelada.")
        return

    # ── Confirmar ────────────────────────────────────────────────────────────
    base   = staged["base"]
    campos = staged["campos"]
    nid    = base.get("notion_id")
    _staged_edits.pop(uid, None)

    if not nid:
        await query.message.reply_text("⚠️ No encontré el gasto para editar. Usa /corregir.")
        return

    ok, g, props, err = await asyncio.to_thread(_aplicar_edicion_notion, base, campos)
    if err == "sin_cambios":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("🤔 No detecté cambios para aplicar.")
        return
    if not ok:
        await query.message.reply_text("❌ No pude actualizar el gasto en Notion.")
        return

    g["seguro"] = True
    guardar_contexto(uid, g)
    if _edicion_cambio_categoria(props):
        await asyncio.to_thread(guardar_aprendizaje, g["concepto"].lower(), g["subcategoria"], g["presupuesto"])

    await query.edit_message_reply_markup(reply_markup=None)
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    await query.message.reply_text(
        msg_gasto(g, notion_id=nid, header="✏️ Gasto actualizado"),
        parse_mode="Markdown"
    )
    await notificar_pareja(context, uid,
        msg_gasto(g, notion_id=nid, header=f"✏️ {nombre} editó un gasto"),
        parse_mode="Markdown"
    )

async def callback_sandbox_edicion(update, context):
    """Confirmación de edición dentro del sandbox (/prueba). No toca Notion ni notifica."""
    query = update.callback_query
    await query.answer()

    staged = context.user_data.get("prueba_staged")
    if not staged:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ No hay edición pendiente." + _FOOTER_SB)
        return

    if query.data == "sandbox_cancel":
        context.user_data.pop("prueba_staged", None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Edición descartada." + _FOOTER_SB)
        return

    # Confirmar — solo actualiza user_data, sin Notion ni notificaciones
    g = _editar_gasto_local(staged["base"], staged["campos"])
    context.user_data["prueba_gasto"] = g
    context.user_data.pop("prueba_staged", None)

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(_msg_sandbox(g, header="✅ Gasto actualizado (simulado)"))

# ── REGISTRAR VIA SHORTCUT (iOS) ─────────────────────────────────────────────
async def registrar_via_shortcut(texto: str, user_id: int):
    """Registra un gasto vía Shortcut/Siri.
    Devuelve (ok: bool, msg: str, resumen: str).
    'resumen' es una línea compacta lista para mostrar en iOS (ej: "Oxxo $45.00 · BBVA12 · Despensa").
    """
    import random
    app = get_app()
    if not app:
        return False, "Bot no disponible", ""
    try:
        if GROQ_API_KEY and not _parece_gasto_estricto(texto):
            tipo, payload = await asyncio.to_thread(clasificar_mensaje_groq, texto)
        else:
            tipo, payload = None, None
        # Vía Shortcut/Siri el intent es registrar; si Groq no devolvió un gasto, usar regex
        gasto = payload if tipo == "gasto" else await asyncio.to_thread(parsear_mensaje, texto)
    except ValueError as e:
        await app.bot.send_message(chat_id=user_id, text=f"❓ {e}\n\nEjemplo: Oxxo 45")
        return False, str(e), ""
    except Exception as e:
        await app.bot.send_message(chat_id=user_id, text=f"❌ Error al procesar: {e}")
        return False, str(e), ""
    ok, nid, err = await asyncio.to_thread(guardar_notion, gasto)
    if not ok:
        logger.error(f"Error Notion via shortcut: {err}")
        await app.bot.send_message(chat_id=user_id, text="❌ Error al guardar en Notion. Intenta de nuevo.")
        return False, f"Error Notion: {err}", ""
    gasto_completo = {**gasto, "notion_id": nid}
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, user_id), daemon=True).start()
    guardar_contexto(user_id, gasto_completo)
    if random.randint(1, 50) == 1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()
    ctx = _BotCtx(app.bot)
    asyncio.create_task(generar_insight_groq(gasto_completo, user_id, ctx))
    asyncio.create_task(verificar_hormiga(gasto_completo, user_id, ctx))
    asyncio.create_task(detectar_anomalia(gasto_completo, user_id, ctx))
    asyncio.create_task(verificar_metas(gasto_completo, user_id, ctx))
    msg = msg_gasto(gasto, notion_id=nid)
    if not gasto.get("seguro"):
        msg += "\n\n⚠️ Categoría inferida — usa /corregir si no es correcta."
    await app.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
    nombre = USUARIOS_NOMBRES.get(user_id, "Alguien")
    await notificar_pareja(ctx, user_id,
        msg_gasto(gasto, nombre=nombre, notion_id=nid),
        parse_mode="Markdown"
    )
    # Línea compacta para mostrar en iOS Shortcuts como confirmación nativa
    resumen = f"{gasto['concepto']} ${gasto['monto']:,.2f} · {gasto['tarjeta']} · {gasto['subcategoria']}"
    return True, msg, resumen

class _BotCtx:
    """Wrapper mínimo para pasar app.bot a funciones que esperan context.bot
    (usado en registrar_via_shortcut, que no tiene contexto PTB)."""
    def __init__(self, bot): self.bot = bot

async def _cancelar_conv(update, context):
    context.user_data.clear()
    limpiar_historial(update.effective_user.id)
    await update.message.reply_text("❌ Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ── CONV FOTO ─────────────────────────────────────────────────────────────────
async def handle_foto(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    if not GROQ_API_KEY and not GOOGLE_VISION_API_KEY:
        await update.message.reply_text("❌ No hay servicio de lectura de tickets configurado.")
        return ConversationHandler.END
    msg_espera = await update.message.reply_text("📸 Analizando ticket…")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    # Intentar con Llama 4 Scout primero (más preciso, sin regex)
    datos = await asyncio.to_thread(analizar_ticket_groq, bytes(image_bytes))

    # Fallback a Google Vision si Groq no está disponible o falla
    if datos is None:
        texto_ocr = await asyncio.to_thread(ocr_ticket, bytes(image_bytes))
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
    sub, pre, seguro = await asyncio.to_thread(inferir_categoria, datos["concepto"])
    productos = datos.get("productos") or []
    concepto_foto = datos["concepto"] + ("*" if productos else "")
    gasto = {
        "concepto": concepto_foto, "monto": datos["monto"],
        "fecha": fecha.strftime("%Y-%m-%d"), "tarjeta": tarjeta,
        "mes": mes, "subcategoria": sub, "presupuesto": pre, "seguro": seguro,
        "productos": productos,
    }
    context.user_data["gasto_foto"] = gasto
    aviso = "\n⚠️ Categoría inferida." if not seguro else ""
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data="foto_confirmar"),
        InlineKeyboardButton("❌ Cancelar",  callback_data="foto_cancelar"),
    ]])
    await msg_espera.edit_text(
        f"📋 Resumen del ticket\n\n"
        f"📌 {gasto['concepto']}\n💵 ${gasto['monto']:,.2f}\n🗓️ {_fecha_compacta(gasto['fecha'])}\n"
        f"💳 {gasto['tarjeta']}\n🧾 {gasto['mes']}\n🏷️ {gasto['subcategoria']}\n🗂️ {gasto['presupuesto']}{aviso}"
        + _texto_desglose(productos),
        reply_markup=kb
    )
    return FOTO_CONFIRMAR

def _texto_desglose(productos, limite=15):
    """Texto compacto del desglose de productos para mostrar en Telegram."""
    if not productos:
        return ""
    lineas = ["\n\n🧾 Desglose:"]
    for p in productos[:limite]:
        nombre = (p.get("nombre") or "").strip()
        if not nombre:
            continue
        precio = p.get("precio")
        if isinstance(precio, (int, float)):
            lineas.append(f"• {nombre} — ${precio:,.2f}")
        else:
            lineas.append(f"• {nombre}")
    if len(productos) > limite:
        lineas.append(f"… y {len(productos) - limite} más")
    return "\n".join(lineas)

async def callback_foto(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "foto_cancelar":
        context.user_data.clear()
        await query.message.edit_text("❌ Registro cancelado.")
        return ConversationHandler.END
    gasto = context.user_data.pop("gasto_foto", None)
    if not gasto:
        await query.message.edit_text(
            "⚠️ El bot se reinició y perdió el ticket. Vuelve a enviar la foto para guardarlo.",
            reply_markup=InlineKeyboardMarkup([])
        )
        return ConversationHandler.END
    ok, nid, err = await asyncio.to_thread(guardar_notion, gasto)
    if not ok:
        logger.error(f"Error guardando ticket en Notion: {err}")
        await query.message.edit_text("❌ Error al guardar en Notion.")
        return ConversationHandler.END
    gasto_completo = {**gasto, "notion_id": nid}
    uid = query.from_user.id
    guardar_contexto(uid, gasto_completo)
    threading.Thread(target=guardar_historial_notion, args=(gasto_completo, uid), daemon=True).start()
    asyncio.create_task(generar_insight_groq(gasto_completo, uid, context))
    asyncio.create_task(verificar_hormiga(gasto_completo, uid, context))
    asyncio.create_task(detectar_anomalia(gasto_completo, uid, context))
    asyncio.create_task(verificar_metas(gasto_completo, uid, context))
    import random
    if random.randint(1, 50) == 1:
        threading.Thread(target=limpiar_aprendizaje, daemon=True).start()

    # Intentar agregar tabla de productos a la página de Notion
    tabla_err = ""
    productos = gasto.get("productos") or []
    if productos:
        children = _bloques_productos(productos)
        if children:
            def _append_tabla():
                r = notion_request(
                    "PATCH", f"{NOTION_API_BASE}/blocks/{nid}/children",
                    headers=nh(), json={"children": children}, timeout=NOTION_T_LONG
                )
                if r is None:
                    return 0, "sin respuesta tras 3 intentos"
                return r.status_code, r.text[:300]
            status, resp_text = await asyncio.to_thread(_append_tabla)
            if status != 200:
                tabla_err = f"HTTP {status}: {resp_text}" if status else resp_text
                logger.error(f"Tabla no guardada (page {nid}): {tabla_err}")

    await query.message.edit_text(msg_gasto(gasto, notion_id=nid), parse_mode="Markdown")
    if tabla_err:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"⚠️ Desglose no guardado en Notion.\nError: {tabla_err[:300]}"
        )
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    await notificar_pareja(context, uid,
        msg_gasto(gasto, nombre=nombre, notion_id=nid),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ── CONV GASTO ───────────────────────────────────────────────────────────────
async def handle_gasto(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    return await _procesar_conversacion(update, context, update.message.text.strip(), update.effective_user.id)

async def handle_voice(update, context):
    """Mensaje de voz → transcribe con Whisper → mismo flujo conversacional que el texto."""
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    uid = update.effective_user.id
    if not GROQ_API_KEY:
        await update.message.reply_text("🎤 Para usar audio necesito GROQ_API_KEY configurada.")
        return ConversationHandler.END
    voz = update.message.voice or update.message.audio
    if not voz:
        return ConversationHandler.END
    msg_espera = await update.message.reply_text("🎤 Escuchando…")
    try:
        file = await context.bot.get_file(voz.file_id)
        audio_bytes = await file.download_as_bytearray()
    except Exception:
        await msg_espera.edit_text("🤔 No pude descargar el audio.")
        return ConversationHandler.END
    texto = await asyncio.to_thread(groq_transcribir, bytes(audio_bytes), "audio.ogg")
    if not texto:
        await msg_espera.edit_text("🤔 No pude entender el audio. Intenta de nuevo.")
        return ConversationHandler.END
    await msg_espera.edit_text(f"🎤 Entendí: {texto}")
    return await _procesar_conversacion(update, context, texto, uid)

async def _registrar_multiples(update, context, gastos, uid):
    """Registra una lista de gastos ya construidos (de Groq) y manda confirmación agrupada."""
    lineas, ok_list = [], []
    for g in gastos[:5]:
        ok, nid, err = await asyncio.to_thread(guardar_notion, g)
        if ok:
            gc = {**g, "notion_id": nid}
            threading.Thread(target=guardar_historial_notion, args=(gc, uid), daemon=True).start()
            guardar_contexto(uid, gc)
            lineas.append(f"📌 {g['concepto']} ${g['monto']:,.2f}")
            ok_list.append(gc)
        else:
            lineas.append(f"❌ {g['concepto']} (error Notion)")
    encabezado = f"✅ {len(ok_list)} gastos registrados" if len(ok_list) != 1 else "✅ 1 gasto registrado"
    await update.message.reply_text(encabezado + "\n" + "\n".join(lineas), reply_markup=ReplyKeyboardRemove())
    nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
    if ok_list:
        for g in ok_list:
            await notificar_pareja(context, uid,
                msg_gasto(g, nombre=nombre, notion_id=g["notion_id"]),
                parse_mode="Markdown"
            )

async def _manejar_referencia(texto: str, uid: int, update, context) -> bool:
    """
    Detecta mensajes que referencian el contexto anterior sin ser un gasto nuevo.
    Maneja: links de Notion, eliminar, el más caro/barato.
    Retorna True si respondió (shortcircuit), False para continuar flujo normal.
    """
    t = texto.lower().strip()

    # ── "dame el link" / "link de notion" ────────────────────────────────────
    es_link = any(p in t for p in [
        "dame el link", "dáme el link", "dame links", "los links",
        "link de notion", "link del", "ver en notion", "ábreme", "abre el link",
    ])
    if es_link:
        results  = mem_get_results(uid)
        last_g   = mem_get_gasto(uid)
        items    = results if results else ([last_g] if last_g.get("notion_id") else [])
        if not items:
            await update.message.reply_text("🤷 No tengo resultados recientes. Haz una consulta primero.")
            return True
        # Filtros de ítem específico
        if any(p in t for p in ["primer", "primero"]):
            items = items[:1]
        elif any(p in t for p in ["segundo"]):
            items = items[1:2] if len(items) > 1 else items[:1]
        elif any(p in t for p in ["último", "ultimo", "el último"]):
            items = items[-1:]
        elif not any(p in t for p in ["ambos", "los dos", "todos", "todas"]):
            items = items[:3]  # máximo 3 si no especifica
        links = []
        for item in items:
            nid = item.get("notion_id", "")
            if nid:
                url = f"https://notion.so/{nid}"
                links.append(f"• [{item.get('concepto','Gasto')} ${item.get('monto',0):,.0f}]({url})")
        if links:
            await update.message.reply_text(
                "\n".join(links), parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await update.message.reply_text("⚠️ No encontré IDs de Notion en los resultados recientes.")
        return True

    # ── "elimínalo" / "bórralo" → last_gasto ─────────────────────────────────
    es_eliminar = any(p in t for p in [
        "elimínalo", "elimínala", "bórralo", "bórrala",
        "eliminalo", "borralo", "elimina el último", "borra el último",
    ])
    if es_eliminar:
        last_g = mem_get_gasto(uid)
        if not last_g.get("notion_id"):
            # También revisar _ultimo_gasto_usuario como fallback
            ug = obtener_contexto(uid)
            if ug and ug.get("notion_id"):
                last_g = {"concepto": ug.get("concepto",""), "monto": ug.get("monto",0),
                          "notion_id": ug.get("notion_id",""), "fecha": str(ug.get("fecha",""))}
        if not last_g.get("notion_id"):
            await update.message.reply_text(
                "🤷 No sé a qué gasto te refieres. Usa /eliminar para buscarlo.")
            return True
        context.user_data["gasto_eliminar"] = last_g
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑️ Sí, eliminar", callback_data="elim_si"),
            InlineKeyboardButton("❌ No",            callback_data="elim_no"),
        ]])
        await update.message.reply_text(
            f"¿Eliminar *{last_g['concepto']}* ${last_g['monto']:,.2f}?",
            reply_markup=kb, parse_mode="Markdown")
        return True

    # ── "el más caro" / "el más barato" → operación sobre last_results ───────
    if any(p in t for p in ["más caro", "el mayor", "el más alto"]):
        results = mem_get_results(uid)
        if not results:
            return False
        top = max(results, key=lambda r: r.get("monto", 0))
        nid = top.get("notion_id", "")
        msg = f"💰 El más caro: *{top['concepto']}* ${top['monto']:,.0f}"
        if nid:
            msg += f"\n[Ver en Notion](https://notion.so/{nid})"
        await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
        return True

    if any(p in t for p in ["más barato", "el menor", "el más chico", "el más económico"]):
        results = mem_get_results(uid)
        if not results:
            return False
        low = min(results, key=lambda r: r.get("monto", 0))
        nid = low.get("notion_id", "")
        msg = f"💸 El más barato: *{low['concepto']}* ${low['monto']:,.0f}"
        if nid:
            msg += f"\n[Ver en Notion](https://notion.so/{nid})"
        await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
        return True

    return False

async def _procesar_conversacion(update, context, texto, uid):
    # 0) Cargar memoria persistente (no-op si ya está en RAM esta sesión)
    await mem_cargar(uid)

    # 0.5) Pre-proceso: detectar referencias al contexto anterior antes de clasificar
    if await _manejar_referencia(texto, uid, update, context):
        return ConversationHandler.END

    # 1) Clasificar con Groq cuando el mensaje NO tiene formato estricto.
    #    Distingue gasto / consulta / edición → evita registrar gastos al preguntar.
    gasto_groq = None
    groq_fue_llamado = False
    # Expandir aliases ANTES de clasificar (solo si no es una definición de alias)
    texto = await asyncio.to_thread(expandir_aliases, uid, texto)
    if GROQ_API_KEY and not _parece_gasto_estricto(texto):
        groq_fue_llamado = True
        ultimo = obtener_contexto(uid)
        tipo, payload = await asyncio.to_thread(clasificar_mensaje_groq, texto, ultimo, obtener_historial(uid))
        if tipo == "consulta":
            if await responder_consulta_groq(texto, uid, update, context):
                return ConversationHandler.END
            await update.message.reply_text("🤔 No pude consultar eso ahorita. Intenta reformularlo.")
            return ConversationHandler.END
        if tipo == "edicion" and ultimo:
            # Acumular en staging area: mostrar propuesta con botones antes de aplicar a Notion
            staged = _staged_edits.get(uid, {})
            # Si el gasto base cambió (registraron uno nuevo), descartar staged anterior
            if staged and staged.get("base", {}).get("notion_id") != ultimo.get("notion_id"):
                staged = {}
            campos_merged = {**staged.get("campos", {}), **payload}
            base = staged.get("base") or ultimo
            preview = _editar_gasto_local(base, campos_merged)
            _staged_edits[uid] = {"campos": campos_merged, "base": base}
            nid = base.get("notion_id", "")
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confirmar", callback_data="edicion_confirm"),
                InlineKeyboardButton("❌ Cancelar",  callback_data="edicion_cancel"),
            ]])
            await _responder(update, context,
                msg_gasto(preview, notion_id=nid, header="📝 Propuesta de cambio"),
                reply_markup=kb, parse_mode="Markdown")
            return ConversationHandler.END
        if tipo == "multi_gasto" and payload:
            await _registrar_multiples(update, context, payload, uid)
            return ConversationHandler.END
        if tipo == "meta" and payload:
            presupuesto = payload.get("presupuesto", "TOTAL")
            limite      = payload.get("limite", 0)
            ciclo       = mes_activo_str()
            ok = await asyncio.get_event_loop().run_in_executor(None, guardar_meta, uid, presupuesto, limite, ciclo)
            label = "total del ciclo" if presupuesto == "TOTAL" else presupuesto
            if ok:
                agregar_historial(uid, "assistant", f"Guardé meta: {label} ${limite:,.0f} para {ciclo}.")
                await update.message.reply_text(
                    f"🎯 Meta guardada: *{label}* ≤ ${limite:,.0f} en {ciclo}\n\nTe aviso cuando llegues al 80% y al 100%.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ No pude guardar la meta. Intenta de nuevo.")
            return ConversationHandler.END
        if tipo == "ingreso" and payload:
            monto_i = payload.get("monto", 0)
            ciclo   = payload.get("ciclo") or mes_activo_str()
            ok = await asyncio.get_event_loop().run_in_executor(None, guardar_meta, uid, "INGRESO", monto_i, ciclo)
            if ok:
                # Mostrar posición financiera inmediata
                gasto_r = await asyncio.to_thread(ejecutar_consulta_finanzas, {"meses": [ciclo]})
                gastado = gasto_r["total"]
                pct = (gastado / monto_i * 100) if monto_i else 0
                resto = monto_i - gastado
                agregar_historial(uid, "assistant", f"Ingreso estimado ${monto_i:,.0f} guardado para {ciclo}.")
                await update.message.reply_text(
                    f"💰 Ingreso estimado para *{ciclo}*: ${monto_i:,.0f}\n\n"
                    f"📊 Gasto actual: ${gastado:,.0f} ({pct:.0f}%)\n"
                    f"💚 Saldo libre: ${resto:,.0f}\n\n"
                    f"Puedes actualizar el ingreso en cualquier momento.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ No pude guardar el ingreso estimado. Intenta de nuevo.")
            return ConversationHandler.END
        if tipo == "alias" and payload:
            trigger  = payload.get("trigger", "")
            resolved = payload.get("resolved", "")
            ok = await asyncio.get_event_loop().run_in_executor(None, guardar_alias, uid, trigger, resolved)
            if ok:
                agregar_historial(uid, "assistant", f"Guardé alias: '{trigger}' → '{resolved}'.")
                await update.message.reply_text(
                    f"✅ Guardado. Cuando digas *{trigger}* entiendo _{resolved}_.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ No pude guardar el alias. Intenta de nuevo.")
            return ConversationHandler.END
        if tipo == "listar_aliases":
            aliases = await asyncio.to_thread(_cargar_aliases_uid, uid)
            if not aliases:
                await update.message.reply_text("No tienes aliases guardados aún.")
            else:
                lineas = [f"• *{a['trigger']}* → _{a['resolved']}_" for a in aliases]
                await update.message.reply_text(
                    "📋 *Tus aliases:*\n" + "\n".join(lineas), parse_mode="Markdown")
            return ConversationHandler.END
        if tipo == "borrar_alias" and payload:
            trigger_b = payload.get("trigger", "")
            ok = await asyncio.to_thread(borrar_alias, uid, trigger_b)
            if ok:
                await update.message.reply_text(f"✅ Alias *{trigger_b}* eliminado.", parse_mode="Markdown")
            else:
                await update.message.reply_text(
                    f"❌ No encontré el alias '{trigger_b}'. Usa '¿qué aliases tengo?' para ver la lista.")
            return ConversationHandler.END
        if tipo == "reporte" and payload:
            subtipo_r = payload.get("subtipo", "semanal")
            await update.message.reply_text(f"📊 Generando reporte {subtipo_r}…")
            await enviar_reporte(subtipo_r, solo_a=uid)
            if subtipo_r == "mensual":
                ok_email = await enviar_reporte_email_mensual()
                if ok_email:
                    await update.message.reply_text("📧 Reporte detallado enviado a tu correo.")
            return ConversationHandler.END
        if tipo == "accion" and payload:
            await update.message.reply_text("🔍 Buscando gastos afectados…")
            preview, gastos = await asyncio.to_thread(_accion_preview, payload)
            if not gastos:
                await update.message.reply_text(preview)
                return ConversationHandler.END
            context.user_data["accion_pendiente"] = {"payload": payload, "gastos": gastos}
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confirmar", callback_data="accion_confirmar"),
                InlineKeyboardButton("❌ Cancelar",  callback_data="accion_cancelar"),
            ]])
            await update.message.reply_text(preview, reply_markup=kb, parse_mode="Markdown")
            return ConversationHandler.END
        if tipo == "gasto":
            gasto_groq = payload
        elif tipo == "otro":
            await update.message.reply_text("🤔 No entendí. ¿Quieres registrar un gasto?\nEjemplo: Starbucks 150")
            return ConversationHandler.END

    # 2) Múltiples gastos separados por coma (solo si Groq no intervino y hay comas)
    #    Cuando Groq procesó el mensaje no usamos comma-split (evita parsear NL con comas).
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    if not groq_fue_llamado and gasto_groq is None and len(partes) > 1:
        lineas = []
        gastos_ok = []
        for parte in partes:
            try:
                gasto = await asyncio.to_thread(parsear_mensaje, parte)
                ok, nid, err = await asyncio.to_thread(guardar_notion, gasto)
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
        nombre = USUARIOS_NOMBRES.get(uid, "Alguien")
        if gastos_ok:
            for g in gastos_ok:
                await notificar_pareja(context, uid,
                    msg_gasto(g, nombre=nombre, notion_id=g["notion_id"]),
                    parse_mode="Markdown"
                )
        return ConversationHandler.END

    # 3) Gasto único (de Groq o del parser estricto/regex)
    try:
        gasto = gasto_groq or await asyncio.to_thread(parsear_mensaje, texto)
        if gasto["monto"]>=MONTO_INUSUAL:
            context.user_data["gasto_pendiente"]=gasto
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confirmar", callback_data="monto_si"),
                InlineKeyboardButton("❌ Cancelar",  callback_data="monto_no"),
            ]])
            await update.message.reply_text(
                f"⚠️ El monto ${gasto['monto']:,.2f} es inusual.\n¿Confirmas '{gasto['concepto']}'?",
                reply_markup=kb)
            return CONFIRMAR_MONTO
        if not gasto["seguro"]:
            context.user_data["gasto_pendiente"]=gasto
            await update.message.reply_text(
                f"❓ No reconoci '{gasto['concepto']}'.\n¿En qué categoría va?",
                reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
            return CONFIRMAR_CAT
        await registrar_y_notificar(update,context,gasto)
    except ValueError as e:
        if groq_fue_llamado:
            await update.message.reply_text("❓ No pude registrar ese gasto.\n\nEjemplo: Starbucks 150")
        else:
            await update.message.reply_text(f"❓ {e}\n\nEjemplo: Starbucks 150")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def callback_confirmar_monto(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    gasto = context.user_data.pop("gasto_pendiente", None)
    if query.data == "monto_si" and gasto:
        await query.edit_message_text(f"✅ Confirmado: {gasto['concepto']} ${gasto['monto']:,.2f}")
        await registrar_y_notificar(update, context, gasto)
    else:
        await query.edit_message_text("❌ Gasto cancelado.")
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
    if grp not in GRUPOS_CAT:
        # Texto no reconocido como grupo válido (p.ej. duplicado de webhook o mensaje libre)
        # Quedamos en CONFIRMAR_CAT sin tocar gasto_pendiente
        await update.message.reply_text(
            "❓ Elige una categoría con los botones:",
            reply_markup=ReplyKeyboardMarkup(menu_grupos(), one_time_keyboard=True, resize_keyboard=True))
        return CONFIRMAR_CAT
    subcats = GRUPOS_CAT.get(grp)
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
    await asyncio.to_thread(guardar_aprendizaje, gasto["concepto"].lower(), gasto["subcategoria"], gasto["presupuesto"])
    await registrar_y_notificar(update, context, gasto)
    return ConversationHandler.END

async def confirmar_subcat(update, context):
    txt = update.message.text.strip()
    if txt == BTN_CANCELAR:
        return await _cancelar_conv(update, context)
    grp = context.user_data.get("grupo_pendiente", "")
    subcats_validas = GRUPOS_CAT.get(grp, [])
    if subcats_validas and txt not in subcats_validas:
        # Texto no es una subcategoría válida — repetir menú sin tocar gasto_pendiente
        menu = [[s] for s in subcats_validas] + [[BTN_CANCELAR]]
        await update.message.reply_text(
            "❓ Elige una subcategoría con los botones:",
            reply_markup=ReplyKeyboardMarkup(menu, one_time_keyboard=True, resize_keyboard=True))
        return CONFIRMAR_SUBCAT
    gasto = context.user_data.pop("gasto_pendiente", None)
    context.user_data.pop("grupo_pendiente", None)
    if not gasto:
        await update.message.reply_text("Error.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    gasto["subcategoria"] = txt
    gasto["presupuesto"]  = limpiar_emoji(grp)
    await asyncio.to_thread(guardar_aprendizaje, gasto["concepto"].lower(), txt, limpiar_emoji(grp))
    await registrar_y_notificar(update, context, gasto)
    context.user_data.clear()
    return ConversationHandler.END

# ── CONV CORREGIR ────────────────────────────────────────────────────────────
_NUM_EMOJI = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]

def _lista_corregir(ultimos):
    lineas = ["✏️ Elige el gasto (1-5):", ""]
    for i, g in enumerate(ultimos):
        num = _NUM_EMOJI[i] if i < len(_NUM_EMOJI) else f"{i+1}."
        lineas.append(f"{num} {g['concepto']} · ${g['monto']:,.2f}")
    return "\n".join(lineas)

async def cmd_corregir(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    uid = update.effective_user.id
    ultimos = await asyncio.to_thread(cargar_historial_compartido)
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
    except (ValueError, IndexError, KeyError):
        await update.message.reply_text(
            "❓ Escribe el número del gasto (1-5) o usa ❌ Cancelar.",
            reply_markup=ReplyKeyboardMarkup(menu_elegir(context.user_data.get("historial_corregir",[])),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_ELEGIR
    # El historial puede estar viejo si el gasto ya se corrigió: releemos lo vigente de Notion.
    nid = gasto.get("notion_id")
    if nid:
        actual = await asyncio.to_thread(_base_desde_notion, nid)
        if actual:
            gasto = {**gasto, **{k: v for k, v in actual.items() if v not in ("", None)}}
    await update.message.reply_text("✏️ Editor abierto:", reply_markup=ReplyKeyboardRemove())
    return await _abrir_panel(update, context, gasto)

# ── PANEL DE EDICIÓN MULTI-CAMPO (híbrido botones + texto) ────────────────────
GRUPOS_LISTA = list(GRUPOS_CAT.keys())
_CAMPOS_PANEL = ("monto", "fecha", "tarjeta", "subcategoria", "presupuesto", "concepto")
_CAMPOS_LABEL = {
    "monto": "💵 Monto", "fecha": "🗓️ Fecha", "tarjeta": "💳 Tarjeta",
    "subcategoria": "🏷️ Categoría", "presupuesto": "🗂️ Presupuesto", "concepto": "📝 Concepto",
}

def _nombre_relacion(props, campo, inv):
    rel = props.get(campo, {}).get("relation", [])
    if not rel:
        return ""
    rid = rel[0].get("id", "").replace("-", "")
    return inv.get(rid, "")

def _base_desde_notion(nid):
    """Lee un gasto existente de Notion para poblar el panel (entrada desde notificación)."""
    r = notion_request("GET", f"{NOTION_API_BASE}/pages/{nid}", headers=nh(), timeout=NOTION_T_DEFAULT)
    if not r or r.status_code != 200:
        return None
    p = r.json().get("properties", {})
    titulo = p.get("Concepto", {}).get("title", [])
    concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
    monto = p.get("Monto", {}).get("number", 0) or 0
    fecha = (p.get("Fecha", {}).get("date", {}) or {}).get("start", "")
    pago = p.get("Pago", {}).get("select")
    tarjeta = (pago.get("name") if pago else "") or notion_rich_text(p, "Estado de Cuenta")
    return {"notion_id": nid, "concepto": concepto, "monto": monto, "fecha": fecha,
            "tarjeta": tarjeta, "mes": "",
            "subcategoria": _nombre_relacion(p, "Subcategoria", SC_INV),
            "presupuesto":  _nombre_relacion(p, "Presupuesto", PR_INV)}

def _valor_actual(base, campo):
    if campo == "monto":
        return f"${(base.get('monto') or 0):,.2f}"
    if campo == "fecha":
        return _fecha_compacta(base["fecha"]) if base.get("fecha") else "—"
    return base.get(campo) or "—"

def _valor_nuevo_str(campo, val):
    if campo == "monto":
        try: return f"${float(val):,.2f}"
        except (ValueError, TypeError): return str(val)
    if campo == "fecha":
        try: return _fecha_compacta(val)
        except Exception: return str(val)
    return str(val)

def _resumen_cambios(base, cambios):
    """Bloque de texto con los cambios pendientes (antes → después). Vacío si no hay cambios."""
    if not cambios:
        return ""
    lineas = [f"📝 Cambios pendientes ({len(cambios)}):"]
    for campo in _CAMPOS_PANEL:
        if campo in cambios:
            lineas.append(f"   • {_CAMPOS_LABEL[campo]}: {_valor_actual(base, campo)} → {_valor_nuevo_str(campo, cambios[campo])}")
    return "\n".join(lineas)

def _con_cambios(prompt, base, cambios):
    """Antepone el resumen de cambios pendientes a un texto de submenú, para no perderlo de vista."""
    resumen = _resumen_cambios(base, cambios)
    return f"{resumen}\n\n{prompt}" if resumen else prompt

def _panel_corregir(base, cambios):
    """Devuelve (texto, InlineKeyboardMarkup) del panel con los valores actuales y pendientes."""
    lineas = [f"✏️ Editando: {base.get('concepto') or 'Gasto'}", ""]
    for campo in _CAMPOS_PANEL:
        label = _CAMPOS_LABEL[campo]
        if campo in cambios:
            lineas.append(f"{label}: {_valor_actual(base, campo)} → {_valor_nuevo_str(campo, cambios[campo])} ✏️")
        else:
            lineas.append(f"{label}: {_valor_actual(base, campo)}")
    resumen = _resumen_cambios(base, cambios)
    if resumen:
        lineas += ["", "━━━━━━━━━━━━━━", resumen]
    lineas += ["", "Toca un campo para cambiarlo, o escribe el cambio (ej: \"monto 95\")."]
    n = len(cambios)
    aplicar_txt = f"✅ Aplicar ({n})" if n else "✅ Aplicar"
    botones = [
        [InlineKeyboardButton("💵 Monto", callback_data="edit:f:monto"),
         InlineKeyboardButton("🗓️ Fecha", callback_data="edit:f:fecha")],
        [InlineKeyboardButton("💳 Tarjeta", callback_data="edit:f:tarjeta"),
         InlineKeyboardButton("🏷️ Categoría", callback_data="edit:f:subcategoria")],
        [InlineKeyboardButton("🗂️ Presupuesto", callback_data="edit:f:presupuesto"),
         InlineKeyboardButton("📝 Concepto", callback_data="edit:f:concepto")],
        [InlineKeyboardButton(aplicar_txt, callback_data="edit:apply"),
         InlineKeyboardButton("❌ Cancelar", callback_data="edit:cancel")],
    ]
    return "\n".join(lineas), InlineKeyboardMarkup(botones)

async def _abrir_panel(update, context, base):
    context.user_data["corr_base"] = base
    context.user_data["corr_cambios"] = {}
    context.user_data["corr_esperando"] = None
    chat_id = update.effective_chat.id
    texto, kb = _panel_corregir(base, {})
    msg = await context.bot.send_message(chat_id, texto, reply_markup=kb)
    context.user_data["corr_msg_id"] = msg.message_id
    context.user_data["corr_chat_id"] = chat_id
    return CORREGIR_PANEL

async def _editar_panel(query, base, cambios):
    texto, kb = _panel_corregir(base, cambios)
    try:
        await query.edit_message_text(texto, reply_markup=kb)
    except Exception:
        pass  # "message is not modified" u otros — ignorable

def _parse_valor_campo(campo, txt):
    """Valida un valor escrito a mano. Devuelve (ok, valor, mensaje_error)."""
    if campo == "monto":
        try:
            v = float(txt.replace("$", "").replace(",", ""))
            if v <= 0:
                raise ValueError
            return True, v, ""
        except ValueError:
            return False, None, "❓ Escribe un monto válido (ej: 150)."
    if campo == "fecha":
        try:
            return True, datetime.date.fromisoformat(txt).strftime("%Y-%m-%d"), ""
        except ValueError:
            pass
        f, leftover = parsear_fecha([txt.lower()])
        if not leftover:   # parsear_fecha consumió el token → entendió la fecha
            return True, f.strftime("%Y-%m-%d"), ""
        return False, None, "❓ Fecha no válida. Usa: ayer, 15-may o 2026-05-15."
    if campo == "concepto":
        return (True, txt.title(), "") if txt else (False, None, "❓ Concepto vacío.")
    return False, None, "❓ Campo desconocido."

async def _abrir_campo(query, context, campo, base, cambios):
    """Despliega el sub-editor del campo: texto libre o botones según el campo."""
    if campo in ("monto", "fecha", "concepto"):
        context.user_data["corr_esperando"] = campo
        prompts = {
            "monto":    "💵 Envía el nuevo monto (ej: 150).",
            "fecha":    "🗓️ Envía la nueva fecha (ej: ayer, 15-may, 2026-05-15).",
            "concepto": "📝 Envía el nuevo concepto.",
        }
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="edit:back")]])
        await query.edit_message_text(_con_cambios(prompts[campo], base, cambios), reply_markup=kb)
        return CORREGIR_PANEL
    if campo == "tarjeta":
        botones = []
        fila = []
        for t in TARJETAS_VALIDAS:
            emoji = TARJETA_EMOJI.get(t, "💳")
            fila.append(InlineKeyboardButton(f"{emoji} {t}", callback_data=f"edit:v:tarjeta:{t}"))
            if len(fila) == 2:
                botones.append(fila); fila = []
        if fila: botones.append(fila)
        botones.append([InlineKeyboardButton("⬅️ Volver", callback_data="edit:back")])
        await query.edit_message_text(_con_cambios("💳 Elige la tarjeta:", base, cambios), reply_markup=InlineKeyboardMarkup(botones))
        return CORREGIR_PANEL
    if campo == "subcategoria":
        botones, fila = [], []
        for i, grp in enumerate(GRUPOS_LISTA):
            fila.append(InlineKeyboardButton(grp, callback_data=f"edit:g:{i}"))
            if len(fila) == 2:
                botones.append(fila); fila = []
        if fila: botones.append(fila)
        botones.append([InlineKeyboardButton("⬅️ Volver", callback_data="edit:back")])
        await query.edit_message_text(_con_cambios("🏷️ Elige la categoría principal:", base, cambios), reply_markup=InlineKeyboardMarkup(botones))
        return CORREGIR_PANEL
    if campo == "presupuesto":
        nombres = [k for k in PR.keys() if k != "Deudas"]   # evita el alias duplicado
        botones, fila = [], []
        for nombre in nombres:
            emoji = PR_EMOJI.get(nombre, "")
            label = f"{emoji} {nombre}" if emoji else nombre
            fila.append(InlineKeyboardButton(label, callback_data=f"edit:v:pre:{nombre}"))
            if len(fila) == 2:
                botones.append(fila); fila = []
        if fila: botones.append(fila)
        botones.append([InlineKeyboardButton("⬅️ Volver", callback_data="edit:back")])
        await query.edit_message_text(_con_cambios("🗂️ Elige el presupuesto:", base, cambios), reply_markup=InlineKeyboardMarkup(botones))
        return CORREGIR_PANEL
    return CORREGIR_PANEL

async def panel_callback(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in USUARIOS_AUTORIZADOS:
        return CORREGIR_PANEL
    base = context.user_data.get("corr_base")
    cambios = context.user_data.get("corr_cambios", {})
    if base is None:
        await query.edit_message_text("⚠️ Sesión expirada. Usa /corregir de nuevo.")
        return ConversationHandler.END
    data = query.data
    context.user_data["corr_esperando"] = None

    if data == "edit:cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelado.")
        return ConversationHandler.END

    if data == "edit:back":
        await _editar_panel(query, base, cambios)
        return CORREGIR_PANEL

    if data == "edit:apply":
        if not cambios:
            await context.bot.send_message(update.effective_chat.id,
                "ℹ️ Aún no has cambiado nada. Toca un campo primero.")
            return CORREGIR_PANEL
        await query.edit_message_text("⏳ Aplicando cambios…")
        await aplicar_edicion_contextual(update, context, dict(cambios), base)
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("edit:f:"):
        return await _abrir_campo(query, context, data.split(":", 2)[2], base, cambios)

    if data.startswith("edit:g:"):
        grp = GRUPOS_LISTA[int(data.split(":", 2)[2])]
        subcats = GRUPOS_CAT.get(grp, [grp])
        if len(subcats) == 1:
            cambios["subcategoria"] = subcats[0]
            context.user_data["corr_cambios"] = cambios
            await _editar_panel(query, base, cambios)
            return CORREGIR_PANEL
        botones = []
        fila_s = []
        for s in subcats:
            emoji_s = SC_EMOJI.get(s, "")
            label_s = f"{emoji_s} {s}" if emoji_s else s
            fila_s.append(InlineKeyboardButton(label_s, callback_data=f"edit:v:sub:{s}"))
            if len(fila_s) == 2:
                botones.append(fila_s); fila_s = []
        if fila_s: botones.append(fila_s)
        botones.append([InlineKeyboardButton("⬅️ Volver", callback_data="edit:f:subcategoria")])
        await query.edit_message_text(_con_cambios(f"🏷️ {grp} — elige la subcategoría:", base, cambios), reply_markup=InlineKeyboardMarkup(botones))
        return CORREGIR_PANEL

    if data.startswith("edit:v:"):
        _, _, tipo, val = data.split(":", 3)
        if   tipo == "tarjeta": cambios["tarjeta"] = val
        elif tipo == "pre":     cambios["presupuesto"] = val
        elif tipo == "sub":     cambios["subcategoria"] = val
        context.user_data["corr_cambios"] = cambios
        await _editar_panel(query, base, cambios)
        return CORREGIR_PANEL

    return CORREGIR_PANEL

async def panel_texto(update, context):
    """Texto durante el panel: o el valor de un campo pedido, o una frase libre (híbrido)."""
    base = context.user_data.get("corr_base")
    if base is None:
        return ConversationHandler.END
    cambios = context.user_data.get("corr_cambios", {})
    txt = update.message.text.strip()
    esperando = context.user_data.get("corr_esperando")

    if esperando:
        ok, valor, err = _parse_valor_campo(esperando, txt)
        if not ok:
            await update.message.reply_text(err)
            return CORREGIR_PANEL
        cambios[esperando] = valor
        context.user_data["corr_esperando"] = None
    else:
        tipo, payload = (await asyncio.to_thread(clasificar_mensaje_groq, txt, base)) if GROQ_API_KEY else (None, None)
        if tipo == "edicion" and payload:
            cambios.update(payload)
        else:
            await update.message.reply_text(
                "🤔 No entendí. Toca un botón del panel o escribe algo como \"monto 95\".")
            return CORREGIR_PANEL

    context.user_data["corr_cambios"] = cambios
    texto, kb = _panel_corregir(base, cambios)
    chat_id = context.user_data.get("corr_chat_id", update.effective_chat.id)
    msg_id  = context.user_data.get("corr_msg_id")
    try:
        await context.bot.edit_message_text(texto, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
    except Exception:
        msg = await context.bot.send_message(chat_id, texto, reply_markup=kb)
        context.user_data["corr_msg_id"] = msg.message_id
    return CORREGIR_PANEL

# ── SANDBOX DE PRUEBA ────────────────────────────────────────────────────────

_FOOTER_SB = "\n\n— Sandbox activo · nada se guarda · /cancelar para salir"

def _msg_sandbox(gasto: dict, header: str = "🧪 Gasto simulado", origen: str = "") -> str:
    """Formatea la tarjeta de un gasto simulado con footer de sandbox."""
    fecha_fmt = datetime.datetime.strptime(gasto["fecha"], "%Y-%m-%d").strftime("%d/%b/%y").upper()
    lineas = [
        f"{header}\n",
        f"📌 {gasto['concepto']}",
        f"💵 ${gasto['monto']:,.2f}",
        f"🗓️ {fecha_fmt}",
        f"💳 {gasto['tarjeta']}",
        f"🧾 {gasto['mes']}",
        f"🏷️ {gasto['subcategoria']}",
        f"🗂️ {gasto['presupuesto']}",
    ]
    if origen:
        lineas.append(f"\n🔍 {origen}")
    return "\n".join(lineas) + _FOOTER_SB

def _editar_gasto_local(gasto: dict, campos: dict) -> dict:
    """Aplica campos de edición sobre un gasto dict sin tocar Notion. Devuelve gasto modificado."""
    g = dict(gasto)
    recompute = False

    if campos.get("monto") is not None:
        try:
            g["monto"] = float(campos["monto"])
        except (ValueError, TypeError):
            pass
    if campos.get("concepto"):
        g["concepto"] = str(campos["concepto"]).title()
    if campos.get("tarjeta") in TARJETAS_VALIDAS:
        g["tarjeta"] = campos["tarjeta"]
        recompute = True
    if campos.get("fecha"):
        try:
            g["fecha"] = datetime.date.fromisoformat(campos["fecha"]).strftime("%Y-%m-%d")
            recompute = True
        except (ValueError, TypeError):
            pass
    if recompute:
        f = datetime.date.fromisoformat(g["fecha"])
        g["mes"] = calcular_mes(f, g["tarjeta"])
    if campos.get("presupuesto") in PR:
        g["presupuesto"] = campos["presupuesto"]
    if campos.get("subcategoria") in SC:
        g["subcategoria"] = campos["subcategoria"]
        # Auto-derivar presupuesto si no vino explícito (igual que en edición real)
        if not campos.get("presupuesto") and g["subcategoria"] in SUBCAT_PRESUPUESTO:
            pr_d = SUBCAT_PRESUPUESTO[g["subcategoria"]]
            if pr_d in PR:
                g["presupuesto"] = pr_d
    return g

async def cmd_prueba(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    context.user_data.pop("prueba_gasto", None)
    await update.message.reply_text(
        "🧪 Sandbox activado — escribe gastos y correcciones libremente.\n"
        "Nada se guarda en Notion.\n\n"
        "→ Escribe un gasto para empezar · /cancelar para salir"
    )
    return PRUEBA_GASTO

async def handle_prueba(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    texto = update.message.text.strip()
    gasto_actual = context.user_data.get("prueba_gasto")

    try:
        gasto = None
        origen_label = ""

        # ── Ruta Groq ────────────────────────────────────────────────────────
        if GROQ_API_KEY and not _parece_gasto_estricto(texto):
            tipo, payload = await asyncio.to_thread(
                clasificar_mensaje_groq, texto, gasto_actual
            )

            # Edición sobre gasto existente en sandbox — staging con confirmación
            if tipo == "edicion" and payload and gasto_actual:
                prev_staged = context.user_data.get("prueba_staged", {})
                campos_merged = {**prev_staged.get("campos", {}), **payload}
                preview = _editar_gasto_local(gasto_actual, campos_merged)
                context.user_data["prueba_staged"] = {"campos": campos_merged, "base": gasto_actual}
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Confirmar", callback_data="sandbox_confirm"),
                    InlineKeyboardButton("❌ Cancelar",  callback_data="sandbox_cancel"),
                ]])
                await update.message.reply_text(
                    _msg_sandbox(preview, header="📝 Propuesta de cambio"), reply_markup=kb
                )
                return PRUEBA_GASTO

            # Multi-gasto
            if tipo == "multi_gasto" and payload:
                lineas = [f"🧪 Multi-gasto detectado ({len(payload)} elementos)\n"]
                for i, g in enumerate(payload, 1):
                    lineas.append(f"#{i}  📌 {g['concepto']} · 💵 ${g['monto']:,.2f}")
                    lineas.append(f"     💳 {g['tarjeta']} · 🧾 {g['mes']} · 🏷️ {g['subcategoria']} · 🗂️ {g['presupuesto']}")
                context.user_data["prueba_gasto"] = payload[0]
                await update.message.reply_text("\n".join(lineas) + _FOOTER_SB)
                return PRUEBA_GASTO

            # Consulta / otro / no es gasto
            if tipo in ("consulta", "otro", "meta", "alias", "ingreso"):
                hint = "\n\nEscribe un gasto para empezar." if not gasto_actual else ""
                await update.message.reply_text(
                    f"🧪 Groq clasificó esto como: {tipo}{hint}" + _FOOTER_SB
                )
                return PRUEBA_GASTO

            # Nuevo gasto via Groq
            if tipo == "gasto" and payload:
                gasto = payload
                sub, pre, seguro, ori_emoji, ori_txt = await asyncio.to_thread(inferir_categoria_con_origen, gasto["concepto"])
                gasto.update({"subcategoria": sub, "presupuesto": pre, "seguro": seguro})
                origen_label = f"Groq + {ori_emoji} {ori_txt}"

        # ── Parser clásico (fallback o formato estricto) ─────────────────────
        if gasto is None:
            hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
            tokens = texto.split()
            fecha, tokens2 = parsear_fecha(tokens)
            texp,  tokens2 = parsear_tarjeta(tokens2)
            monto, tokens2 = parsear_monto(tokens2)
            concepto = " ".join(tokens2).strip()
            if not concepto: raise ValueError("No encontré el concepto")
            if monto is None: raise ValueError("No encontré el monto")
            tarjeta = calcular_tarjeta(fecha, texp)
            mes     = calcular_mes(fecha, tarjeta)
            sub, pre, seguro, ori_emoji, ori_txt = await asyncio.to_thread(inferir_categoria_con_origen, concepto)
            gasto = {
                "concepto": concepto.title(), "monto": monto,
                "fecha": fecha.strftime("%Y-%m-%d"), "tarjeta": tarjeta,
                "mes": mes, "subcategoria": sub, "presupuesto": pre,
            }
            origen_label = f"{ori_emoji} {ori_txt}"

        context.user_data["prueba_gasto"] = gasto
        await update.message.reply_text(_msg_sandbox(gasto, origen=origen_label))
        return PRUEBA_GASTO

    except ValueError as e:
        hint = "\n\nEjemplo: Starbucks 150" if not gasto_actual else ""
        await update.message.reply_text(f"❓ {e}{hint}" + _FOOTER_SB)
        return PRUEBA_GASTO
    except Exception as e:
        await update.message.reply_text(f"❌ Error inesperado: {e}" + _FOOTER_SB)
        return PRUEBA_GASTO

async def cancelar(update,context):
    context.user_data.clear()
    limpiar_historial(update.effective_user.id)
    await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def start(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return
    nombre = USUARIOS_NOMBRES.get(update.effective_user.id, "")
    await update.message.reply_text(
        f"Hola {nombre} 👋 soy tu bot de gastos personal.\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "💸 *Anotar un gasto*\n"
        "Escríbelo directo, con voz 🎤 o foto del ticket 📸\n"
        "`Starbucks 150`\n"
        "`Gasolina 500 BBVA05 ayer`\n"
        "`Walmart 350 15-may`\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "🔍 *Pregúntame lo que quieras*\n"
        "Entiendo lenguaje natural:\n"
        "• _¿Cuánto gasté ayer?_\n"
        "• _¿En qué semana del mes gasto más?_\n"
        "• _¿Está subiendo mi gasto en Restaurantes?_\n"
        "• _¿Cuándo fui por última vez a Costco?_\n"
        "• _¿Cuáles son mis gastos fijos cada mes?_\n"
        "• _¿Cuánto me ahorraría si dejo Starbucks?_\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "📋 *Comandos*\n"
        "/resumen — resumen del mes activo\n"
        "/estadisticas — este mes vs el anterior\n"
        "/reporte — reporte semanal o mensual\n"
        "/top — top 5 gastos del mes\n"
        "/buscar — buscar por concepto\n"
        "/corregir — cambiar categoría o monto\n"
        "/eliminar — borrar el último gasto\n\n"

        "💳 BBVA05 · BBVA12 · HEYB25 · BMEX04 · EFVO",
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

    await update.message.reply_text(f"⏳ Comparando {mes_ant} vs {mes_act}…")

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

def _fecha_compacta(fecha):
    """Fecha compacta dd/MMM/yy en español (ej: 18/MAY/26). Vacío si no hay fecha."""
    if not fecha:
        return ""
    d = datetime.datetime.strptime(fecha, "%Y-%m-%d")
    return f"{d.day:02d}/{MESES_ESP[d.month]}/{str(d.year)[-2:]}"

MESES_ESP_LARGO = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                   7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}

def _fecha_larga(fecha):
    """Fecha estilizada en español (ej: 18 de mayo, 2026). Para el correo mensual."""
    if not fecha:
        return ""
    d = datetime.datetime.strptime(fecha, "%Y-%m-%d")
    return f"{d.day} de {MESES_ESP_LARGO[d.month]}, {d.year}"

def _esc_md(s: str) -> str:
    """Escapa caracteres especiales de Markdown V1 en texto dinámico (conceptos, etc.)."""
    for ch in ("_", "*", "`", "["):
        s = s.replace(ch, "\\" + ch)
    return s

def _trunc(s: str, n: int) -> str:
    """Recorta un texto a n caracteres con … final para mantener columnas alineadas."""
    s = s.strip()
    return s if len(s) <= n else s[:n-1] + "…"

async def cmd_buscar(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return
    q = " ".join(context.args).strip()
    if not q:
        await update.message.reply_text("🔍 Uso: /buscar <texto>\nEjemplo: /buscar uber")
        return
    await update.message.reply_text(f"🔍 Buscando \"{q}\"…")

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
    filas = []
    suma = 0
    for page in resultados:
        concepto, monto, fecha = _gasto_props(page)
        suma += monto
        nom = _trunc(concepto, 14).ljust(14)
        monto_s = f"${monto:,.0f}".rjust(7)
        filas.append(f"{nom}  {monto_s}  {_fecha_compacta(fecha)}")
    msg = (
        f"🔍 *{_esc_md(q)}* — {len(resultados)} resultado(s)\n\n"
        f"```\n\n{chr(10).join(filas)}\n```\n\n"
        f"💰 *Suma mostrada*   ${suma:,.0f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_top(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return
    mes = context.args[0].upper() if context.args else mes_activo_str()
    mid = await asyncio.to_thread(buscar_mes_id, mes)
    if not mid:
        await update.message.reply_text(f"❌ No encontré el mes {mes} en Notion.")
        return
    await update.message.reply_text(f"⏳ Top gastos de {mes}…")

    def _top():
        gastos = query_notion_db(NOTION_DATABASE_ID, {"property": "Mes", "relation": {"contains": mid}})
        items = [_gasto_props(g) for g in gastos]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:5]

    top = await asyncio.to_thread(_top)
    if not top:
        await update.message.reply_text(f"📭 No hay gastos en {mes}.")
        return
    filas = []
    for i, (concepto, monto, fecha) in enumerate(top):
        num = _NUM_EMOJI[i] if i < len(_NUM_EMOJI) else f"{i+1}."
        filas.append(f"{num} {_esc_md(concepto)} · ${monto:,.2f}")
    msg = f"🏆 *Top 5 — {_esc_md(mes)}*\n\n" + "\n".join(filas)
    await update.message.reply_text(msg, parse_mode="Markdown")

# ── REPORTES PROACTIVOS (semanal / mensual) ──────────────────────────────────

MX_TZ = pytz.timezone("America/Mexico_City")

async def job_reporte_semanal():
    """Job APScheduler: reporte semanal — lunes 9am MX"""
    try:
        await enviar_reporte(tipo="semanal")
        logger.info("[APScheduler] Reporte semanal enviado OK")
    except Exception as e:
        logger.error(f"[APScheduler] Error reporte semanal: {e}")

async def job_reporte_mensual():
    """Job APScheduler: reporte mensual — día 5 2pm MX"""
    try:
        await enviar_reporte(tipo="mensual")
        ok = await enviar_reporte_email_mensual()
        logger.info(f"[APScheduler] Reporte mensual enviado OK (email: {ok})")
    except Exception as e:
        logger.error(f"[APScheduler] Error reporte mensual: {e}")

def _mes_anterior(codigo: str) -> str:
    """'JUN26' → 'MAY26'. Retrocede un ciclo."""
    nombre, aa = codigo[:3], codigo[3:]
    num = next((k for k, v in MESES_ESP.items() if v == nombre), 1)
    anio = 2000 + int(aa)
    if num == 1:
        num, anio = 12, anio - 1
    else:
        num -= 1
    return f"{MESES_ESP[num]}{str(anio)[-2:]}"

def _agg_gastos(gastos: list) -> dict:
    """Agrega una lista de páginas de gastos de Notion: total, por categoría, por tarjeta, items."""
    total, cats, tarjetas, items = 0.0, {}, {}, []
    for g in gastos:
        props = g.get("properties", {})
        m = props.get("Monto", {}).get("number", 0) or 0
        total += m
        pr = _presupuesto_de_props(props)
        if pr:
            cats[pr] = cats.get(pr, 0) + m
        t = _leer_tarjeta(props) or "?"
        tarjetas[t] = tarjetas.get(t, 0) + m
        titulo = props.get("Concepto", {}).get("title", [])
        concepto = titulo[0].get("text", {}).get("content", "") if titulo else ""
        fecha = (props.get("Fecha", {}).get("date", {}) or {}).get("start", "")
        items.append((concepto, m, fecha))
    return {"total": total, "conteo": len(items), "por_categoria": cats, "por_tarjeta": tarjetas, "items": items}

def _agg_ciclo(mes: str) -> dict:
    """Agrega los gastos de un ciclo (relación Mes) de Notion."""
    mid = buscar_mes_id(mes)
    if not mid:
        return {"total": 0.0, "conteo": 0, "por_categoria": {}, "por_tarjeta": {}, "items": []}
    gastos = query_notion_db(NOTION_DATABASE_ID, {"property": "Mes", "relation": {"contains": mid}})
    return _agg_gastos(gastos)

def _datos_reporte(tipo: str = "semanal") -> dict:
    """Datos para el reporte simple (Telegram). Semanal=últimos 7 días; Mensual=ciclo recién cerrado."""
    hoy = datetime.datetime.now(zoneinfo.ZoneInfo("America/Mexico_City")).date()
    if tipo == "mensual":
        cerrado = _mes_anterior(mes_activo_str())
        a, b = _agg_ciclo(cerrado), _agg_ciclo(_mes_anterior(cerrado))
        return {"tipo": "mensual", "periodo": f"el ciclo {cerrado}", "titulo": f"Reporte {cerrado}",
                "total": a["total"], "conteo": a["conteo"],
                "por_categoria": a["por_categoria"], "por_tarjeta": a.get("por_tarjeta", {}),
                "total_prev": b["total"]}
    ini, fin_prev = hoy - datetime.timedelta(days=6), hoy - datetime.timedelta(days=7)
    ini_prev = ini - datetime.timedelta(days=7)

    def agg(d1, d2):
        gastos = query_notion_db(NOTION_DATABASE_ID, {"and": [
            {"property": "Fecha", "date": {"on_or_after": d1.isoformat()}},
            {"property": "Fecha", "date": {"on_or_before": d2.isoformat()}}]})
        a = _agg_gastos(gastos)
        return a["total"], a["conteo"], a["por_categoria"], a["por_tarjeta"]

    total, n, cats, tarjetas_sem = agg(ini, hoy)
    total_prev, _, _, _ = agg(ini_prev, fin_prev)
    return {"tipo": "semanal", "periodo": "esta semana", "titulo": "Reporte semanal",
            "total": total, "conteo": n, "por_categoria": cats, "por_tarjeta": tarjetas_sem,
            "total_prev": total_prev}

async def enviar_reporte(tipo: str = "semanal", solo_a: int = None):
    """Reporte SIMPLE a Telegram (a ambos o a uno). Lenguaje natural con fallback."""
    app = get_app()
    if not app:
        return
    d = await asyncio.to_thread(_datos_reporte, tipo)
    cats = sorted(d["por_categoria"].items(), key=lambda x: x[1], reverse=True)
    resumen_cats = ", ".join(f"{k}=${v:,.0f}" for k, v in cats[:6])
    tarjetas_ord = sorted(d.get("por_tarjeta", {}).items(), key=lambda x: x[1], reverse=True)
    resumen_tarj = ", ".join(f"{k}=${v:,.0f}" for k, v in tarjetas_ord if k != "?")

    if d["conteo"] == 0:
        texto = f"📊 {d['titulo']}: no hay gastos registrados en el periodo."
    else:
        diff = d["total"] - d["total_prev"]
        texto = None
        if GROQ_API_KEY:
            tarj_block = f"\n- Por tarjeta: {resumen_tarj}" if resumen_tarj else ""
            prompt = f"""Escribe el reporte semanal de gastos de Jordi y Nani en español mexicano. Tono cálido y directo. Máximo 180 palabras.

Datos reales (NO inventes nada que no esté aquí):
- Total {d['periodo']}: ${d['total']:,.0f} en {d['conteo']} gastos
- Periodo anterior: ${d['total_prev']:,.0f} (diferencia ${diff:+,.0f}){tarj_block}
- Por categoría (mayor a menor): {resumen_cats}

Estructura obligatoria:
1. Encabezado con saludo, total y comparativa vs semana anterior (1 oración).
2. Desglose por categoría en bullet list (• Categoría: $monto) — solo las que tengan datos.
3. Si hay desglose por tarjeta, un bullet list corto con eso también.
4. Cierra con 1 observación financiera concreta basada en los datos (no genérica) y 1 emoji de cierre.

Usa $ con separador de miles. No menciones datos que no aparezcan arriba."""
            texto = await asyncio.to_thread(groq_completar, prompt, 450)
        if not texto:
            flecha = "🔺" if diff > 0 else ("🔻" if diff < 0 else "➡️")
            tarj_line = f"\n💳 Tarjetas: {resumen_tarj}" if resumen_tarj else ""
            texto = (f"📊 *{d['titulo']}*\n\n"
                     f"💰 Total: ${d['total']:,.0f}  ({d['conteo']} gastos)\n"
                     f"{flecha} vs anterior: ${d['total_prev']:,.0f}\n\n{resumen_cats}{tarj_line}")

    destinos = [solo_a] if solo_a else list(USUARIOS_AUTORIZADOS)
    for uid in destinos:
        try:
            await app.bot.send_message(chat_id=uid, text=texto)
        except Exception as e:
            logger.warning(f"No pude enviar reporte a {uid}: {e}")

# ── REPORTE MENSUAL DETALLADO POR CORREO (Resend + HTML) ─────────────────────
def enviar_email_resend(asunto: str, html: str) -> bool:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY no configurado — email omitido")
        return False
    try:
        r = requests.post("https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "Bot Gastos <onboarding@resend.dev>", "to": [REPORTE_EMAIL],
                  "subject": asunto, "html": html}, timeout=15)
        if r.status_code in (200, 201):
            return True
        logger.error(f"Resend error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Error enviando email: {e}")
    return False

def _datos_mensual_detallado() -> dict:
    cerrado = _mes_anterior(mes_activo_str())
    previo = _mes_anterior(cerrado)
    a, b = _agg_ciclo(cerrado), _agg_ciclo(previo)
    cats = []
    for k in sorted(set(a["por_categoria"]) | set(b["por_categoria"]),
                    key=lambda x: a["por_categoria"].get(x, 0), reverse=True):
        v = a["por_categoria"].get(k, 0)
        cats.append((k, v, v - b["por_categoria"].get(k, 0)))
    top = sorted(a["items"], key=lambda x: x[1], reverse=True)[:6]
    msi = []
    for c, m, _f in a["items"]:
        mm = re.search(r'(\d{1,2})\s*/\s*(\d{1,2})', c)
        if mm:
            msi.append((c, m, int(mm.group(1)), int(mm.group(2))))
    alertas = [(k, dd) for k, v, dd in cats
               if dd > 800 and b["por_categoria"].get(k, 0) > 0 and v > b["por_categoria"].get(k, 0) * 1.4]
    return {"cerrado": cerrado, "previo": previo, "total": a["total"], "total_prev": b["total"],
            "conteo": a["conteo"], "cats": cats, "top": top, "msi": msi, "alertas": alertas,
            "promedio": a["total"] / 30 if a["total"] else 0}

def _html_reporte_mensual(d: dict, recom_html: str = "") -> str:
    diff = d["total"] - d["total_prev"]
    pct = (diff / d["total_prev"] * 100) if d["total_prev"] else 0
    col = "#dc2626" if diff > 0 else "#16a34a"
    signo = "▲" if diff > 0 else ("▼" if diff < 0 else "=")
    maxcat = max((v for _, v, _ in d["cats"]), default=1) or 1
    filas = ""
    for k, v, dd in d["cats"][:12]:
        pctv = (v / d["total"] * 100) if d["total"] else 0
        ancho = max(2, int(v / maxcat * 100))
        dcol = "#dc2626" if dd > 0 else ("#16a34a" if dd < 0 else "#9ca3af")
        filas += (
            f'<tr>'
            f'<td style="padding:8px 6px;font:14px -apple-system,Arial,sans-serif;color:#111;">{k}'
            f'<div style="margin-top:4px;height:6px;background:#eef2f5;border-radius:4px;">'
            f'<div style="height:6px;width:{ancho}%;background:#0f766e;border-radius:4px;"></div></div></td>'
            f'<td style="padding:8px 6px;font:600 14px -apple-system,Arial,sans-serif;color:#111;text-align:right;white-space:nowrap;">${v:,.0f}</td>'
            f'<td style="padding:8px 6px;font:13px -apple-system,Arial,sans-serif;color:#6b7280;text-align:right;">{pctv:.0f}%</td>'
            f'<td style="padding:8px 6px;font:13px -apple-system,Arial,sans-serif;color:{dcol};text-align:right;white-space:nowrap;">{dd:+,.0f}</td>'
            f'</tr>')
    tops = "".join(
        f'<li style="margin:6px 0;font:14px -apple-system,Arial,sans-serif;color:#111;">{c} — '
        f'<b>${m:,.0f}</b> <span style="color:#9ca3af;">· {_fecha_larga(f)}</span></li>'
        for c, m, f in d["top"])
    msi_html = ""
    if d["msi"]:
        items = "".join(
            f'<li style="margin:6px 0;font:14px -apple-system,Arial,sans-serif;color:#111;">{c} — '
            f'${m:,.0f} <span style="color:#9ca3af;">(pago {n} de {t})</span></li>'
            for c, m, n, t in d["msi"])
        msi_html = (f'<h3 style="font:600 16px -apple-system,Arial,sans-serif;color:#111;margin:26px 0 8px;">'
                    f'💳 Meses sin intereses activos</h3>'
                    f'<ul style="margin:0;padding-left:18px;">{items}</ul>')
    recom_block = ""
    if recom_html.strip():
        recom_block = (f'<div style="margin-top:26px;padding:16px 18px;background:#f0fdf4;border-radius:10px;'
                       f'border:1px solid #bbf7d0;">{recom_html}</div>')
    return (
        f'<div style="margin:0;padding:24px 12px;background:#f3f4f6;">'
        f'<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;'
        f'box-shadow:0 1px 4px rgba(0,0,0,.08);">'
        f'<div style="background:#0f766e;padding:28px 24px;">'
        f'<div style="font:13px -apple-system,Arial,sans-serif;color:#a7f3d0;letter-spacing:1px;">REPORTE MENSUAL · {d["cerrado"]}</div>'
        f'<div style="font:700 34px -apple-system,Arial,sans-serif;color:#fff;margin-top:6px;">${d["total"]:,.0f}</div>'
        f'<div style="font:14px -apple-system,Arial,sans-serif;color:#d1fae5;margin-top:4px;">'
        f'{signo} ${abs(diff):,.0f} ({pct:+.0f}%) vs ciclo anterior · {d["conteo"]} gastos · ~${d["promedio"]:,.0f}/día</div>'
        f'</div>'
        f'<div style="padding:24px;">'
        f'<h3 style="font:600 16px -apple-system,Arial,sans-serif;color:#111;margin:0 0 8px;">Gasto por categoría</h3>'
        f'<table style="width:100%;border-collapse:collapse;">{filas}</table>'
        f'<h3 style="font:600 16px -apple-system,Arial,sans-serif;color:#111;margin:26px 0 8px;">🏆 Gastos más grandes</h3>'
        f'<ul style="margin:0;padding-left:18px;">{tops}</ul>'
        f'{msi_html}'
        f'{recom_block}'
        f'<p style="margin:26px 0 0;font:12px -apple-system,Arial,sans-serif;color:#9ca3af;text-align:center;">'
        f'Generado automáticamente por tu Bot de Gastos · ciclo {d["cerrado"]} vs {d["previo"]}</p>'
        f'</div></div></div>')

async def enviar_reporte_email_mensual() -> bool:
    if not RESEND_API_KEY:
        return False
    d = await asyncio.to_thread(_datos_mensual_detallado)
    if d["conteo"] == 0:
        return False
    recom = ""
    if GROQ_API_KEY:
        resumen_cats = ", ".join(f"{k}=${v:,.0f}(Δ{dd:+,.0f})" for k, v, dd in d["cats"][:8])
        msi_txt = ", ".join(c for c, _, _, _ in d["msi"]) or "ninguno"
        prompt = f"""Eres el asesor financiero personal de Jordi y Nani (México). Datos reales del ciclo {d['cerrado']}:
- Total: ${d['total']:,.0f} (ciclo anterior ${d['total_prev']:,.0f})
- Categorías con cambio vs ciclo anterior: {resumen_cats}
- Compras a meses sin intereses activas: {msi_txt}

Escribe en español mexicano, conciso, al grano y sin redundancias. Devuelve SOLO fragmento HTML (sin <html> ni <body>) con exactamente dos secciones:
<h3 style="font:600 16px -apple-system,Arial,sans-serif;color:#065f46;margin:0 0 8px;">💡 Recomendaciones</h3>
<ul>...2 a 3 acciones concretas para el próximo ciclo...</ul>
<h3 style="font:600 16px -apple-system,Arial,sans-serif;color:#065f46;margin:16px 0 8px;">📌 A tener en cuenta</h3>
<ul>...cargos/MSI o categorías a vigilar...</ul>
Interpreta las cifras, no las repitas tal cual. No inventes nada."""
        recom = await asyncio.to_thread(groq_completar, prompt, 500) or ""
        recom = re.sub(r'^```(?:html)?\s*', '', recom.strip())
        recom = re.sub(r'\s*```$', '', recom.strip())
    html = _html_reporte_mensual(d, recom)
    return await asyncio.to_thread(enviar_email_resend, f"📊 Tu reporte de gastos — {d['cerrado']}", html)

async def cmd_reporte(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return
    texto_cmd = (update.message.text or "").lower()
    tipo = "mensual" if ("mensual" in texto_cmd or (context.args and "mes" in context.args[0].lower())) else "semanal"
    await update.message.reply_text(f"📊 Generando reporte {tipo}…")
    await enviar_reporte(tipo, solo_a=update.effective_user.id)
    if tipo == "mensual":
        ok = await enviar_reporte_email_mensual()
        await update.message.reply_text("📧 Reporte detallado enviado a tu correo." if ok
                                        else "⚠️ No pude enviar el correo (revisa RESEND_API_KEY).")

async def cmd_eliminar(update, context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    uid = update.effective_user.id
    historial = cargar_historial_notion(uid)
    if not historial:
        await update.message.reply_text("No hay gastos recientes para eliminar.")
        return ConversationHandler.END
    ultimo = historial[0]
    # El Historial Bot puede estar desactualizado si el gasto se corrigió después.
    # Releemos los valores vigentes de la BD principal para mostrar el estado real.
    nid = ultimo.get("notion_id")
    if nid:
        actual = await asyncio.to_thread(_base_desde_notion, nid)
        if actual:
            ultimo = {**ultimo, **{k: v for k, v in actual.items() if v not in ("", None)}}
    context.user_data["gasto_eliminar"] = ultimo
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑️ Sí, eliminar", callback_data="elim_si"),
        InlineKeyboardButton("❌ No",            callback_data="elim_no"),
    ]])
    await update.message.reply_text(
        f"🗑️ ¿Eliminar este gasto?\n\n"
        f"📌 {ultimo['concepto']}\n"
        f"💵 ${ultimo['monto']:,.2f}\n"
        f"🗓️ {_fecha_compacta(ultimo['fecha'])}\n"
        f"🏷️ {ultimo['subcategoria']}  •  {ultimo['presupuesto']}",
        reply_markup=kb
    )
    return ELIMINAR_CONFIRM

async def callback_eliminar(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in USUARIOS_AUTORIZADOS:
        return ConversationHandler.END
    if query.data == "elim_no":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelado.")
        return ConversationHandler.END
    gasto = context.user_data.pop("gasto_eliminar", None)
    if not gasto or not gasto.get("notion_id"):
        await query.edit_message_text("❌ No se encontró el gasto en Notion.")
        return ConversationHandler.END
    r = await asyncio.to_thread(notion_request, "PATCH", f"{NOTION_API_BASE}/pages/{gasto['notion_id']}",
        headers=nh(), json={"archived": True}, timeout=NOTION_T_DEFAULT)
    if r and r.status_code == 200:
        await query.edit_message_text(
            f"🗑️ Eliminado\n\n📌 {gasto['concepto']}  ${gasto['monto']:,.2f}"
        )
    else:
        await query.edit_message_text("❌ Error al eliminar en Notion.")
    context.user_data.clear()
    return ConversationHandler.END

# ── WEBHOOK HANDLER ───────────────────────────────────────────────────────────
_ptb_app = None

def get_app():
    global _ptb_app
    return _ptb_app

class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        import asyncio
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        if parsed.path == "/reporte":
            qs = parse_qs(parsed.query)
            secret = qs.get("secret", [""])[0]
            tipo   = qs.get("tipo", ["semanal"])[0]
            SC_SECRET = SHORTCUT_SECRET
            if SC_SECRET and secret != SC_SECRET:
                self.send_response(403); self.end_headers(); self.wfile.write(b'{"ok":false}'); return
            app = get_app()
            loop = getattr(getattr(app, "update_processor", None), "_loop", None)
            if loop:
                asyncio.run_coroutine_threadsafe(enviar_reporte(tipo), loop)
                if tipo == "mensual":
                    asyncio.run_coroutine_threadsafe(enviar_reporte_email_mensual(), loop)
                logger.info(f"/reporte disparado (tipo={tipo})")
            resp = b'{"ok":true}'
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(resp))); self.end_headers()
            self.wfile.write(resp); return
        self.send_response(200); self.send_header("Content-Type","text/plain")
        self.send_header("Content-Length","2"); self.end_headers()
        self.wfile.write(b"OK"); self.wfile.flush()

    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Type","text/plain"); self.end_headers()

    def do_POST(self):
        import asyncio
        path = self.path.split("?")[0]

        if path == "/propuesta_mes":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length)
                data   = json.loads(body.decode("utf-8"))
                SC_SECRET = SHORTCUT_SECRET
                if SC_SECRET and data.get("secret") != SC_SECRET:
                    self.send_response(403); self.send_header("Content-Type","application/json"); self.end_headers()
                    self.wfile.write(b'{"ok":false,"error":"unauthorized"}'); return
                app  = get_app()
                loop = getattr(getattr(app, "update_processor", None), "_loop", None)
                if loop:
                    asyncio.run_coroutine_threadsafe(enviar_propuesta_mes(data), loop)
                    logger.info(f"/propuesta_mes ciclo={data.get('ciclo_nuevo','?')}")
                resp = b'{"ok":true}'
                self.send_response(200); self.send_header("Content-Type","application/json")
                self.send_header("Content-Length", str(len(resp))); self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                logger.error(f"Error en /propuesta_mes: {e}")
                resp = json.dumps({"ok": False, "error": str(e)}).encode()
                self.send_response(500); self.send_header("Content-Type","application/json")
                self.send_header("Content-Length", str(len(resp))); self.end_headers()
                self.wfile.write(resp)
            return

        if path == "/log":
            logger.info(f"/log recibido desde {self.client_address}")
            try:
                length  = int(self.headers.get("Content-Length", 0))
                body    = self.rfile.read(length)
                data    = json.loads(body.decode("utf-8"))
                SC_SECRET = SHORTCUT_SECRET
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
                    ok, msg, resumen = future.result(timeout=NOTION_T_LONG)
                else:
                    logger.error("/log: loop no disponible"); ok, msg, resumen = False, "Loop no disponible", ""
                resp = json.dumps({"ok": ok, "msg": msg, "resumen": resumen}, ensure_ascii=False).encode()
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

async def setup_webhook(app):
    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
    params = {"url": webhook_url, "drop_pending_updates": True}
    if WEBHOOK_SECRET:
        params["secret_token"] = WEBHOOK_SECRET
    await app.bot.set_webhook(**params)
    info = await app.bot.get_webhook_info()
    logger.info(f"Webhook configurado: {info.url}")

    from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats
    CMDS = [
        BotCommand("resumen",      "📊 Resumen del mes activo"),
        BotCommand("estadisticas", "📈 Este mes vs el anterior"),
        BotCommand("reporte",      "📰 Reporte semanal o mensual"),
        BotCommand("top",          "🏆 Top 5 gastos del mes"),
        BotCommand("buscar",       "🔍 Buscar gastos por concepto"),
        BotCommand("corregir",     "✏️ Editar un gasto reciente"),
        BotCommand("eliminar",     "🗑️ Eliminar el último gasto"),
        BotCommand("prueba",       "🧪 Simular un gasto sin registrar"),
        BotCommand("cancelar",     "❌ Cancelar acción en curso"),
        BotCommand("start",        "👋 Ver instrucciones"),
    ]
    # Limpiar TODOS los scopes para evitar conflictos de prioridad
    for scope in (BotCommandScopeDefault(), BotCommandScopeAllPrivateChats()):
        try:
            await app.bot.delete_my_commands(scope=scope)
        except Exception:
            pass
    # Escribir en Default y AllPrivateChats (este último tiene más prioridad en chats privados)
    await app.bot.set_my_commands(CMDS, scope=BotCommandScopeDefault())
    await app.bot.set_my_commands(CMDS, scope=BotCommandScopeAllPrivateChats())
    logger.info("Comandos de Telegram actualizados en todos los scopes")

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
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gasto),
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
        ],
        states={
            CONFIRMAR_MONTO:  [CallbackQueryHandler(callback_confirmar_monto, pattern="^monto_")],
            CONFIRMAR_CAT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_cat)],
            CONFIRMAR_SUBCAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_subcat)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar), CommandHandler("start", start)],
        # allow_reentry=False (default): el entry_point es TEXT genérico, si fuera True
        # cada texto en estado CONFIRMAR_CAT reinicaría la conv en lugar de ir a confirmar_cat
    )
    conv_corregir = ConversationHandler(
        entry_points=[CommandHandler("corregir", cmd_corregir)],
        states={
            CORREGIR_ELEGIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, corregir_elegir)],
            CORREGIR_PANEL: [
                CallbackQueryHandler(panel_callback, pattern="^edit:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, panel_texto),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)], allow_reentry=True,
    )
    conv_eliminar = ConversationHandler(
        entry_points=[CommandHandler("eliminar", cmd_eliminar)],
        states={ELIMINAR_CONFIRM: [CallbackQueryHandler(callback_eliminar, pattern="^elim_")]},
        fallbacks=[CommandHandler("cancelar", cancelar)], allow_reentry=True,
    )

    app.add_handler(CallbackQueryHandler(callback_edicion,         pattern="^edicion_"))
    app.add_handler(CallbackQueryHandler(callback_sandbox_edicion, pattern="^sandbox_"))
    app.add_handler(CallbackQueryHandler(callback_propuesta,       pattern="^propuesta_"))
    app.add_handler(CallbackQueryHandler(callback_accion,          pattern="^accion_"))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", cmd_resumen))
    app.add_handler(CommandHandler("estadisticas", cmd_estadisticas))
    app.add_handler(CommandHandler("buscar", cmd_buscar))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("reporte", cmd_reporte))
    app.add_handler(conv_prueba)
    app.add_handler(conv_foto)
    app.add_handler(conv_corregir)
    app.add_handler(conv_eliminar)
    app.add_handler(conv_gasto)
    # Fallbacks globales — actúan solo cuando ningún ConversationHandler activo los reclamó
    # (ej. bot reiniciado; el estado de la conversación se perdió)
    app.add_handler(CallbackQueryHandler(callback_foto, pattern="^foto_"))
    app.add_handler(CommandHandler("cancelar", cancelar))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(setup_webhook(app))
    loop.run_until_complete(app.start())
    app.update_processor._loop = loop

    # ── APScheduler ──────────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone=MX_TZ)
    scheduler.add_job(
        job_reporte_semanal,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=MX_TZ),
        id="reporte_semanal", replace_existing=True,
    )
    scheduler.add_job(
        job_reporte_mensual,
        CronTrigger(day=5, hour=14, minute=0, timezone=MX_TZ),
        id="reporte_mensual", replace_existing=True,
    )
    scheduler.start()
    logger.info("[APScheduler] Scheduler iniciado. Jobs: reporte_semanal (lun 9am MX), reporte_mensual (día 5 2pm MX)")

    port = int(os.environ.get("PORT", 10000))
    logger.info(f"HTTP en {port}")
    # ThreadingHTTPServer: cada request en su propio hilo — un /log lento o un
    # webhook pesado ya no bloquea el health check de UptimeRobot ni otros webhooks.
    server = ThreadingHTTPServer(("0.0.0.0", port), WebhookHandler)
    threading.Thread(target=loop.run_forever, daemon=True).start()
    logger.info("Bot corriendo 27.9.0 — fix: allow_reentry=True en conv_gasto rompía CONFIRMAR_CAT")
    server.serve_forever()

if __name__ == "__main__":
    main()
