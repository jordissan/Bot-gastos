import os, re, datetime, requests, threading, unicodedata
from difflib import SequenceMatcher
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

TELEGRAM_TOKEN        = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN          = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID    = os.environ["NOTION_DATABASE_ID"]
NOTION_APRENDIZAJE_ID = "3ba6f37c717948a1a6aeac3b384ff33c"
GOOGLE_MAPS_API_KEY   = os.environ.get("GOOGLE_MAPS_API_KEY", "")

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
    "Impuestos":"224cdb40f1f749c7b5d6e165ad31170d","Entretenimiento":"3547eb0cbb92815d8248db75a759646b",
    "Generosidad":"f4cac9f4b95e4508942ad02ae69ddffe","Iglesia":"89b897bd6fa24b8d897adf380491130e",
    "Personal":"3c42302c396c4f4abffa38bff79ccac6","Departamento":"1af955c917f54a2da39e9bbb8e4032ff",
    "Otros":"1ea7eb0cbb9280cbbe43c1bd54396691",
}

MESES_IDS = {
    "ENE26":"3487eb0cbb92800a9e6fcf9a2d712e40","FEB26":"3487eb0cbb928062b309eecc92f4035e",
    "MAR26":"3487eb0cbb9280648018ffe4171ad173","ABR26":"3447eb0cbb928007822cdf54ad63c9de",
    "MAY26":"3447eb0cbb928051bddee3da069f31f7","JUN26":"3447eb0cbb9280678db1fd1faa5a98cd",
    "JUL26":"3447eb0cbb9280b3ac4bf0106118f576","AGO26":"3447eb0cbb92808daae4d029edda14b7",
    "SEP26":"3447eb0cbb9280ae861bc6db426e8c58","OCT26":"3447eb0cbb928093bf97e20b4540ad79",
    "NOV26":"3447eb0cbb928007b6f5c3fbab7eecd6","DIC26":"3447eb0cbb928049a264d12ff9048685",
}

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

MESES_ESP = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}
MESES_TEXTO = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12,"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}

historial_gastos = []

def normalizar(t):
    t=t.lower().strip(); t=unicodedata.normalize("NFD",t)
    return "".join(c for c in t if unicodedata.category(c)!="Mn")

def similitud(a,b): return SequenceMatcher(None,normalizar(a),normalizar(b)).ratio()
def nh(): return {"Authorization":f"Bearer {NOTION_TOKEN}","Content-Type":"application/json","Notion-Version":"2022-06-28"}

def buscar_aprendizaje(concepto):
    r=requests.post(f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",headers=nh(),json={"filter":{"property":"Concepto","title":{"equals":concepto.lower()}}})
    if r.status_code==200:
        res=r.json().get("results",[])
        if res:
            p=res[0]["properties"]; s=p.get("Subcategoria",{}).get("rich_text",[]); b=p.get("Presupuesto",{}).get("rich_text",[])
            if s and b: return s[0]["text"]["content"],b[0]["text"]["content"]
    return None,None

def guardar_aprendizaje(concepto,sub,pre):
    r=requests.post(f"https://api.notion.com/v1/databases/{NOTION_APRENDIZAJE_ID}/query",headers=nh(),json={"filter":{"property":"Concepto","title":{"equals":concepto.lower()}}})
    if r.status_code==200:
        res=r.json().get("results",[])
        if res:
            pid=res[0]["id"]; u=res[0]["properties"].get("Usos",{}).get("number",0) or 0
            requests.patch(f"https://api.notion.com/v1/pages/{pid}",headers=nh(),json={"properties":{"Subcategoria":{"rich_text":[{"text":{"content":sub}}]},"Presupuesto":{"rich_text":[{"text":{"content":pre}}]},"Usos":{"number":u+1}}})
            return
    requests.post("https://api.notion.com/v1/pages",headers=nh(),json={"parent":{"database_id":NOTION_APRENDIZAJE_ID},"properties":{"Concepto":{"title":[{"text":{"content":concepto.lower()}}]},"Subcategoria":{"rich_text":[{"text":{"content":sub}}]},"Presupuesto":{"rich_text":[{"text":{"content":pre}}]},"Usos":{"number":1}}})

def buscar_maps(concepto):
    if not GOOGLE_MAPS_API_KEY: return None
    try:
        r=requests.post("https://places.googleapis.com/v1/places:searchText",headers={"Content-Type":"application/json","X-Goog-Api-Key":GOOGLE_MAPS_API_KEY,"X-Goog-FieldMask":"places.types"},json={"textQuery":f"{concepto} Guadalajara Mexico","locationBias":{"circle":{"center":{"latitude":20.6597,"longitude":-103.3496},"radius":50000.0}}},timeout=3)
        if r.status_code==200:
            p=r.json().get("places",[])
            if p: return p[0].get("types",[])
    except: pass
    return None

MAPS_TIPOS={"restaurant":("Restaurantes","Restaurantes"),"cafe":("Treat","Diversión"),"bakery":("Treat","Diversión"),"supermarket":("Super","Despensa"),"grocery_or_supermarket":("Super","Despensa"),"convenience_store":("Abarrotes","Despensa"),"gas_station":("Gasolina","Automovil"),"pharmacy":("Medicina","Personal"),"hospital":("Doctor","Personal"),"car_wash":("Mantenimiento","Automovil"),"movie_theater":("Cine","Diversión"),"night_club":("Salidas","Diversión"),"bar":("Salidas","Diversión")}

def cat_maps(tipos):
    if not tipos: return None,None
    for t in tipos:
        for k,v in MAPS_TIPOS.items():
            if k in t: return v
    return None,None

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

def calcular_tarjeta(fecha,exp=None):
    if exp: return exp.upper()
    return "BBVA05" if 5<=fecha.day<=11 else "BBVA12"

def calcular_mes(fecha,tarjeta):
    d,m,y=fecha.day,fecha.month,fecha.year
    if tarjeta=="BBVA05": mp=m+1 if d>=5 else m
    elif tarjeta=="BBVA12": mp=m+2 if d>=12 else m+1
    elif tarjeta=="HEYB25": mp=m+2 if d>=25 else m+1
    elif tarjeta=="BMEX04": mp=m+1 if d>=4 else m
    else: mp=m+1
    while mp>12: mp-=12; y+=1
    return f"{MESES_ESP[mp]}{str(y)[-2:]}"

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

def guardar_notion(gasto):
    props={"Concepto":{"title":[{"text":{"content":gasto["concepto"]}}]},"Monto":{"number":gasto["monto"]},"Fecha":{"date":{"start":gasto["fecha"]}},"Estado de Cuenta":{"rich_text":[{"text":{"content":gasto["tarjeta"]}}]},"Pago":{"select":{"name":gasto["tarjeta"]}}}
    mid=MESES_IDS.get(gasto["mes"])
    if mid: props["Mes"]={"relation":[{"id":mid}]}
    sid=SC.get(gasto["subcategoria"])
    if sid: props["Subcategoria"]={"relation":[{"id":sid}]}
    pid=PR.get(gasto["presupuesto"])
    if pid: props["Presupuesto"]={"relation":[{"id":pid}]}
    r=requests.post("https://api.notion.com/v1/pages",headers=nh(),json={"parent":{"database_id":NOTION_DATABASE_ID},"properties":props})
    return r.status_code==200,r.json().get("id",""),r.text

def actualizar_notion(page_id,sub=None,pre=None):
    props={}
    if sub:
        sid=SC.get(sub)
        if sid: props["Subcategoria"]={"relation":[{"id":sid}]}
    if pre:
        pid=PR.get(pre)
        if pid: props["Presupuesto"]={"relation":[{"id":pid}]}
    r=requests.patch(f"https://api.notion.com/v1/pages/{page_id}",headers=nh(),json={"properties":props})
    return r.status_code==200

def fmt(f):
    from datetime import datetime as dt
    return dt.strptime(f,"%Y-%m-%d").strftime("%d %b %Y").lower()

def msg_gasto(g,nombre=None):
    enc=f"🔔 Nuevo gasto de {nombre}" if nombre else "✅ Gasto guardado"
    return f"{enc}\n\n📌 {g['concepto']}\n💵 ${g['monto']:,.2f}\n🗓️ {fmt(g['fecha'])}\n💳 {g['tarjeta']}  •  Mes: {g['mes']}\n🏷️ {g['subcategoria']}  •  {g['presupuesto']}"

async def registrar_y_notificar(update,context,gasto):
    global historial_gastos
    ok,nid,_=guardar_notion(gasto)
    if not ok:
        await update.message.reply_text("Error al guardar en Notion.",reply_markup=ReplyKeyboardRemove()); return
    historial_gastos.insert(0,{**gasto,"notion_id":nid})
    historial_gastos=historial_gastos[:10]
    await update.message.reply_text(msg_gasto(gasto),reply_markup=ReplyKeyboardRemove())
    uid=update.effective_user.id; notif=USUARIOS_NOTIFICAR.get(uid); nombre=USUARIOS_NOMBRES.get(uid,"Alguien")
    if notif:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Corregir categoría",callback_data=f"cor:{nid}:{gasto['concepto']}")]])
        await context.bot.send_message(chat_id=notif,text=msg_gasto(gasto,nombre=nombre),reply_markup=kb)

# CONV GASTO
async def handle_gasto(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    texto=update.message.text.strip()
    try:
        gasto=parsear_mensaje(texto)
        if gasto["monto"]>=MONTO_INUSUAL:
            context.user_data["gasto_p"]=gasto
            await update.message.reply_text(f"⚠️ El monto ${gasto['monto']:,.2f} es inusual.\n¿Confirmas '{gasto['concepto']}'?",reply_markup=ReplyKeyboardMarkup([["✅ SI","❌ NO"]],one_time_keyboard=True,resize_keyboard=True))
            return CONFIRMAR_MONTO
        if not gasto["seguro"]:
            context.user_data["gasto_p"]=gasto
            await update.message.reply_text(f"❓ No reconoci '{gasto['concepto']}'.\n¿En qué categoría va?",reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
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

# CONV CORREGIR
async def cmd_corregir(update,context):
    if update.effective_user.id not in USUARIOS_AUTORIZADOS: return ConversationHandler.END
    if not historial_gastos:
        await update.message.reply_text("No hay gastos recientes para corregir."); return ConversationHandler.END
    ultimos=historial_gastos[:3]
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
        await update.message.reply_text(
            f"📌 {gasto.get('concepto','')}\n\n¿Qué quieres corregir?",
            reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_QUE
    grp=grupo_key(txt); context.user_data["grupo_elegido"]=grp
    subcats=GRUPOS_CAT.get(grp,[grp])
    if len(subcats)==1:
        context.user_data["nueva_sub"]=subcats[0]
        que=context.user_data.get("que_corregir","")
        if "Ambas" in que:
            await update.message.reply_text(f"Subcategoria: {subcats[0]}\n\n💰 Elige el presupuesto:",reply_markup=ReplyKeyboardMarkup(menu_presupuesto(),one_time_keyboard=True,resize_keyboard=True))
            return CORREGIR_PRESU
        return await aplicar_correccion(update,context,sub=subcats[0])
    menu=[[s] for s in subcats]+[[BTN_REGRESAR,BTN_CANCELAR]]
    await update.message.reply_text(f"🏷️ Elige la subcategoria:",reply_markup=ReplyKeyboardMarkup(menu,one_time_keyboard=True,resize_keyboard=True))
    return CORREGIR_SUBCAT

async def corregir_subcat(update,context):
    txt=update.message.text.strip()
    if txt==BTN_CANCELAR:
        context.user_data.clear(); await update.message.reply_text("❌ Cancelado.",reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    if txt==BTN_REGRESAR:
        await update.message.reply_text("🏷️ Paso 1: Elige la categoría principal:",reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
        return CORREGIR_CAT_GRP
    context.user_data["nueva_sub"]=txt
    que=context.user_data.get("que_corregir","")
    if "Ambas" in que:
        await update.message.reply_text("💰 Elige el presupuesto:",reply_markup=ReplyKeyboardMarkup(menu_presupuesto(),one_time_keyboard=True,resize_keyboard=True))
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
                await update.message.reply_text("🏷️ Elige la subcategoria:",reply_markup=ReplyKeyboardMarkup(menu,one_time_keyboard=True,resize_keyboard=True))
                return CORREGIR_SUBCAT
            await update.message.reply_text("🏷️ Paso 1: Elige la categoría principal:",reply_markup=ReplyKeyboardMarkup(menu_grupos(),one_time_keyboard=True,resize_keyboard=True))
            return CORREGIR_CAT_GRP
        gasto=context.user_data.get("gasto_corregir",{})
        await update.message.reply_text(f"📌 {gasto.get('concepto','')}\n\n¿Qué quieres corregir?",reply_markup=ReplyKeyboardMarkup(menu_que_corregir(),one_time_keyboard=True,resize_keyboard=True))
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
        for g in historial_gastos:
            if g["notion_id"]==gasto["notion_id"]:
                if nueva_sub: g["subcategoria"]=nueva_sub
                if nuevo_pre: g["presupuesto"]=nuevo_pre
        guardar_aprendizaje(gasto["concepto"].lower(),nueva_sub or gasto.get("subcategoria",""),nuevo_pre or gasto.get("presupuesto",""))
        resumen=f"📌 {gasto['concepto']}\n"
        if nueva_sub: resumen+=f"🏷️ Subcategoria: {nueva_sub}\n"
        if nuevo_pre: resumen+=f"💰 Presupuesto: {nuevo_pre}\n"
        await update.message.reply_text(f"✅ Corregido y aprendido\n\n{resumen}",reply_markup=ReplyKeyboardRemove())
        # Notificar al otro usuario
        uid=update.effective_user.id
        nombre=USUARIOS_NOMBRES.get(uid,"Alguien")
        notif=USUARIOS_NOTIFICAR.get(uid)
        if notif:
            msg_correccion=f"✏️ {nombre} corrigió un gasto\n\n{resumen}"
            await context.bot.send_message(chat_id=notif,text=msg_correccion)
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
        "/cancelar — cancelar cualquier accion en curso"
    )

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","text/plain"); self.send_header("Content-Length","2"); self.end_headers(); self.wfile.write(b"OK"); self.wfile.flush()
    def log_message(self,*a): pass

def run_http():
    port=int(os.environ.get("PORT",10000)); print(f"HTTP en {port}")
    HTTPServer(("0.0.0.0",port),H).serve_forever()

def main():
    threading.Thread(target=run_http,daemon=True).start()
    app=Application.builder().token(TELEGRAM_TOKEN).job_queue(None).build()

    conv_gasto=ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND,handle_gasto)],
        states={CONFIRMAR_MONTO:[MessageHandler(filters.TEXT & ~filters.COMMAND,confirmar_monto)],CONFIRMAR_CAT:[MessageHandler(filters.TEXT & ~filters.COMMAND,confirmar_cat)]},
        fallbacks=[CommandHandler("cancelar",cancelar),CommandHandler("start",start)],
        allow_reentry=True,
    )

    conv_corregir=ConversationHandler(
        entry_points=[CommandHandler("corregir",cmd_corregir),CallbackQueryHandler(callback_corregir,pattern="^cor:")],
        states={
            CORREGIR_ELEGIR: [MessageHandler(filters.TEXT & ~filters.COMMAND,corregir_elegir)],
            CORREGIR_QUE:    [MessageHandler(filters.TEXT & ~filters.COMMAND,corregir_que)],
            CORREGIR_CAT_GRP:[MessageHandler(filters.TEXT & ~filters.COMMAND,corregir_cat_grp)],
            CORREGIR_SUBCAT: [MessageHandler(filters.TEXT & ~filters.COMMAND,corregir_subcat)],
            CORREGIR_PRESU:  [MessageHandler(filters.TEXT & ~filters.COMMAND,corregir_presu)],
        },
        fallbacks=[CommandHandler("cancelar",cancelar)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",start))
    app.add_handler(conv_corregir)
    app.add_handler(conv_gasto)
    print("Bot corriendo v_final3...")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
