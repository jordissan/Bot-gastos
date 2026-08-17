"""Configuración del bot: env vars, IDs de Notion, constantes y diccionarios de dominio.
Solo datos — sin lógica ni llamadas de red. Se importa con nombres explícitos
(nunca `import *`: oculta errores de nombre y no trae los que empiezan con "_")."""
import os
import pytz

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

# ── Usuarios y estados de conversación ──────────────────────────────────────
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

# ── Notion: relaciones SC/PR, emojis y API ───────────────────────────────────
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

# Nombres que existen como subcategoría Y como presupuesto, con IDs de Notion
# distintos (Ezra, Restaurantes, Servicios…). El planner debe elegir uno solo:
# se resuelven como subcategoria, que es el filtro más preciso. Se calcula aquí
# para que el prompt nunca quede desincronizado si se agrega una categoría nueva.
NOMBRES_AMBIGUOS = sorted(set(SC) & set(PR))

# Emojis que ocupan 1 celda en monoespaciado (en vez de 2) — necesitan espacio extra
EMOJI_ESTRECHO = {"⛪"}  # Servicios cambió a 💡 (full-width); solo ⛪ sigue siendo angosto

NOTION_API_BASE    = "https://api.notion.com/v1"
NOTION_T_SHORT     = 5
NOTION_T_DEFAULT   = 8
NOTION_T_LONG      = 15

MESES_ESP = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}

# ── Grupos y menús ───────────────────────────────────────────────────────────
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

# ── Reglas de categorización por concepto ────────────────────────────────────
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

# ── Tarjetas ─────────────────────────────────────────────────────────────────
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

HORMIGA_SUBCATS = ("Treat", "Abarrotes", "Restaurantes", "Gasolina")
MX_TZ = pytz.timezone("America/Mexico_City")
