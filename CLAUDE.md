# Bot Gastos — Contexto para Claude Code

> Documento de estado actual del bot (no es un changelog). Describe **lo que el bot hace hoy**
> y cómo está construido. Versión: **v_final24**.

## Resumen del proyecto
Bot de Telegram personal para registrar los gastos de Jordi y Nane, conectado a Notion como base
de datos. Entiende lenguaje natural (texto y voz), lee tickets por foto, responde preguntas sobre
las finanzas y manda reportes. Corre en Render.com con Docker (plan gratuito); UptimeRobot le hace
ping cada 5 min para que el servicio no se duerma.

---

## Stack técnico
- **Lenguaje:** Python 3.11
- **Telegram:** python-telegram-bot==21.3, modo **webhook** (no polling — más estable en Render free tier)
- **Servidor:** Render.com — https://bot-gastos-socj.onrender.com
- **Base de datos:** Notion API (4 bases: Gastos, Aprendizaje, Historial, Balance)
- **IA (Groq):** Llama 3.3 70B (texto), Llama 4 Scout (visión/tickets), Whisper large-v3-turbo (voz)
- **Otras APIs:** Google Maps Places (categorización), Google Vision (OCR de respaldo), Resend (correo)
- **Repositorio:** github.com/jordissan/Bot-gastos (branch: main)

### Modelos Groq
| Uso | Modelo |
|-----|--------|
| Texto (clasificar, planear consultas, redactar) | `llama-3.3-70b-versatile` |
| Visión (leer tickets de foto) | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Voz (transcripción) | `whisper-large-v3-turbo` |

Free tier: ~1,000 req/día. **Si falta `GROQ_API_KEY` o algo falla, el bot cae al comportamiento
clásico (parser de texto estricto) sin romperse.**

---

## Variables de entorno (configuradas en Render)
```
TELEGRAM_TOKEN
NOTION_TOKEN
NOTION_DATABASE_ID    = 9c66972a98e74d5b80df8a7e6569e3ca
NOTION_BALANCE_ID     (meses dinámicos — via env var)
GOOGLE_MAPS_API_KEY
GOOGLE_VISION_API_KEY (misma key que Maps, Vision API habilitada en GCloud)
WEBHOOK_SECRET        (opcional)
RENDER_EXTERNAL_URL   = https://bot-gastos-socj.onrender.com
SHORTCUT_SECRET       (para iOS Shortcut y el endpoint /reporte)
GROQ_API_KEY          (.env local en .gitignore)
RESEND_API_KEY        (envío del reporte mensual por correo)
REPORTE_EMAIL         (destino del reporte mensual; default jor.jorwww@gmail.com)
```

## Usuarios autorizados
| Nombre | Telegram ID | Notifica a |
|--------|-------------|------------|
| Jordi  | 8663298433  | Nane       |
| Nane   | 8093171397  | Jordi      |

Cada gasto/edición que hace uno se le notifica al otro.

## Bases de datos Notion
| BD              | ID                                   | Propósito                            |
|-----------------|--------------------------------------|--------------------------------------|
| Gastos          | `9c66972a98e74d5b80df8a7e6569e3ca`  | Registro principal (fuente de verdad)|
| Aprendizaje Bot | `3ba6f37c717948a1a6aeac3b384ff33c`  | Diccionario de categorías aprendidas |
| Historial Bot   | `35f7eb0cbb9280ae8f02f69b4f242298`  | Últimos 5 gastos por usuario (snapshot)|
| Balance         | via `NOTION_BALANCE_ID` env var      | Meses dinámicos (ENE26, FEB26…) + rollups |
| Metas Bot       | `cf7906bcccfd4690b7ef8c1e996a8e17`  | Metas de gasto por ciclo y presupuesto (por usuario) |
| Alias Bot       | `9000583a97204e6db41994ec96bf5a71`  | Alias personales aprendidos por conversación |

---

# QUÉ PUEDE HACER EL BOT HOY

## 1. Registrar un gasto — 4 vías de entrada
Todas terminan en el mismo "cerebro" (`_procesar_conversacion`) y se guardan en la BD Gastos.

1. **Texto libre / lenguaje natural** — "gasté 200 en el súper", "pagué 350 de gasolina ayer".
2. **Texto en formato estricto** — `Concepto Monto [Tarjeta] [Fecha]` (ej. `Starbucks 150 BBVA05 ayer`).
   Si el mensaje ya trae este formato, se procesa sin llamar al LLM (ahorra API).
3. **Voz** — mensaje de audio; se transcribe con Whisper y se procesa igual que el texto (ver §7).
4. **Foto de ticket** — el bot lee comercio, monto, fecha y el desglose de productos (ver §4).
5. **iOS Shortcut / Siri** — endpoint `POST /log` (mismo flujo, sin update de Telegram).

Detalles del registro:
- Fechas aceptadas: `ayer`, `hoy`, `15-may`, `15/05`. Sin fecha = hoy. Zona: America/Mexico_City.
- Tarjetas: BBVA05, BBVA12, HEYB25, BMEX04, EFVO.
- Si el monto ≥ $5,000 → pide confirmación con **botones inline** ✅ Confirmar / ❌ Cancelar.
- Si no reconoce el concepto → pregunta la categoría (menú de grupos → subcategoría).
- **Varios gastos en un mensaje** se registran de corrido, tanto por coma en formato estricto
  (`super 350, gasolina 500`) como en **lenguaje natural** ("fui al súper 350 y cargué gasolina 500" →
  el clasificador devuelve `multi_gasto`). Confirmación agrupada "✅ N gastos registrados".
- Cada confirmación incluye deep link `🔗 Ver en Notion`.

### Alertas inteligentes al registrar (en background, solo al que registró)
- **Insight de categoría** (`generar_insight_groq`): si la categoría supera ~$3,000 acumulado, comenta.
- **Gasto hormiga** (`verificar_hormiga`): gasto < $150 en Treat/Abarrotes/Restaurantes/Gasolina y ya van
  3+ en esa categoría esta semana → "☕ Llevas N gastos en X esta semana ($total)".
- **Anomalía** (`detectar_anomalia`, matemática pura sin Groq): si el monto supera
  `max(2.5·media, media+2·std)` sobre 5+ registros del mismo concepto → "⚠️ X por $Y parece inusual…".
- Las tres corren vía `asyncio.create_task` y nunca bloquean la confirmación.

## 2. El "cerebro": cómo entiende cada mensaje
`_procesar_conversacion` (lo comparten texto y voz) decide qué hacer:
1. Si el texto **no** tiene formato estricto y hay `GROQ_API_KEY`, `clasificar_mensaje_groq`
   (Llama 3.3 70B) clasifica la intención en **gasto / consulta / edición / otro**.
   Esto evita registrar un gasto por error cuando en realidad estás preguntando algo.
2. Según la intención:
   - **consulta** → `responder_consulta_groq` (ver §3).
   - **edición** → `aplicar_edicion_contextual` sobre el último gasto (ver §5).
   - **gasto** → se registra.
   - **otro** (saludo, charla) → responde "🤔 No entendí…" y termina. No cae al parser.
3. Si Groq no aplica (formato estricto o sin API), usa el parser clásico `parsear_mensaje`.
4. **Multi-gasto por coma** (`super 350, gasolina 500`) solo se intenta cuando **Groq no intervino**
   (`groq_fue_llamado = False`). Si Groq procesó el mensaje, el comma-split se omite para no
   trocear texto de lenguaje natural que contenga comas.

**`_parece_gasto_estricto`:** devuelve `True` (salta Groq) solo si el mensaje tiene **≤ 9 tokens**
y alguno de los últimos 3 es un número. Mensajes más largos (voz, frases naturales) siempre van
a Groq aunque terminen en un número ("…de 150 pesos").

**Memoria conversacional** (`_historial_chat`, últimos 4 turnos por usuario en RAM): el clasificador y
el planner de consultas reciben el contexto reciente para resolver referencias como "¿y ayer?",
"¿y en esa misma categoría?". Se limpia con `/cancelar`. No persiste entre reinicios.

## 3. Consultas en lenguaje natural
Flujo de 2 pasos que evita que el LLM invente cifras:
1. Groq genera un **plan de consulta** (JSON): `{modo, meses, categoria, comercio, fecha_desde, fecha_hasta, anio, historico}`.
2. `ejecutar_consulta_finanzas` / `_datos_consulta_especial` traen los datos **de forma determinística** de Notion.
3. Groq **redacta** la respuesta solo con esos datos reales.

Las fechas de referencia (ayer, semana pasada, esta semana) se **pre-calculan en Python** antes de
pasar al LLM, para que no tenga que hacer aritmética de fechas.

**Tipos de pregunta que responde** (cada uno = un `modo` interno):
| Pregunta de ejemplo | modo |
|---------------------|------|
| "¿cuánto gasté ayer / la semana pasada / el martes?" | `detalle` + `fecha_desde/hasta` (filtra por Fecha real) |
| "¿cuánto gasté este mes / en MAY26 / en restaurantes?" | `detalle` (por ciclo de mes / categoría) |
| "¿cuántas veces fui a Starbucks?" | `detalle` + `comercio` |
| "¿cuánto llevo pagado del Polo / en total / desde siempre?" | `historico: true` (TODA la historia desde 2020) |
| "¿qué año gasté más? / ¿cuánto llevo este año?" | `por_anio` |
| "el gasto más antiguo / más reciente / más caro" | `primero` / `ultimo` / `mayor` |
| "¿en qué se me va el dinero?" | `ranking_categorias` |
| "¿dónde compro más seguido?" | `ranking_frecuencia` (por nº de compras, no monto) |
| "¿cuánto gasto al mes / al día en promedio?" | `promedio_mensual` / `promedio_dia` |
| "¿gasto más entre semana o en fin?" | `dia_semana` |
| "¿qué día del mes gasto más?" | `dia_mas_caro` |
| "¿cómo se reparte mi gasto por semana del mes?" | `semana_mes` |
| "¿voy por encima de mi promedio este mes?" | `desviacion` |
| "¿mi gasto sube o baja últimamente?" | `tendencia` (6 meses) |
| "¿qué mes de 2025 fue el más caro?" | `mes_mas_caro` (usa `anio`) |
| "¿cuáles son mis gastos fijos / recurrentes?" | `recurrentes` (en 3+ de los últimos 6 meses) |
| "¿cuánto llevo sin gastar en X?" | `dias_sin_gasto` (requiere categoría) |
| "¿cuál es mi gasto hormiga?" | `hormiga` (gastos < $150) |
| "¿cuándo fui por última vez a X?" | `ultima_visita` (requiere comercio) |
| "¿cuánto ahorraría si dejara X?" | `proyeccion_ahorro` (requiere comercio) |

- Muchos modos aceptan filtros opcionales `categoria` y/o `meses`.
- Consulta **histórica** (`historico: true`): avisa "🔍 Buscando en toda la historia…" porque
  puede tardar 15-30 s (recorre TODOS los registros desde 2020-01-01); agrega por año.
- Respaldo de presupuesto: si un gasto no tiene relación `Presupuesto` (la columna se borra cada mes
  para resetear la tabla dinámica), el bot deriva la categoría desde la `Subcategoria`
  (`SUBCAT_PRESUPUESTO`), así las consultas por categoría funcionan en cualquier mes histórico.

## 4. Tickets por foto (OCR)
- La foto va directo a Llama 4 Scout (`analizar_ticket_groq`): extrae **comercio, monto, fecha y la
  lista de productos** `[{nombre, precio}]`.
- El desglose se guarda como **tabla Notion** (Producto | Precio) dentro de la página del gasto.
- **Si el ticket tiene productos, el concepto lleva `*` al final** (ej. `Walmart*`) como señal visual
  de que esa página tiene desglose interno.
- El comercio pasa por `normalizar_comercio` (usa `COMERCIOS_OCR`).
- Preview con botones **Confirmar / Cancelar** antes de guardar.
- Fallback a Google Vision (`ocr_ticket` + `parsear_ticket`) si Groq falla.
- Tras confirmar, queda como "último gasto" → se puede editar por frase ("cámbialo a 400").

## 5. Editar y borrar
- **`/corregir` — panel inline multi-campo (híbrido):** muestra los **últimos 5 gastos de ambos
  usuarios combinados** (sin importar quién los registró) para que cualquiera pueda corregir el gasto
  del otro. Eliges el número (1-5) y se abre un panel con teclado en línea y los 6 campos editables:
  **monto, fecha, tarjeta, categoría, presupuesto, concepto**. Apilas varios cambios (se ve un resumen
  "Cambios pendientes") y se aplican **todos en un solo PATCH** al tocar ✅ Aplicar.
  También acepta frases ("monto 95 y tarjeta BBVA05").
  Usa `cargar_historial_compartido()` (sin filtro por UsuarioID).
- **Edición contextual por frase:** justo después de registrar, "cámbialo a 400", "ponlo en
  restaurantes", "fue con BBVA05" editan el último gasto (guardado en RAM).
- Ambas rutas usan la **única** función de escritura `aplicar_edicion_contextual`, que recalcula el
  ciclo de Mes si cambia fecha/tarjeta y aprende la categoría si cambia.
- **`/eliminar`:** archiva el último gasto en Notion (pide confirmación).
- `/corregir` y `/eliminar` **releen los valores vigentes** de la BD principal (vía
  `_base_desde_notion`) antes de mostrar el gasto, para reflejar correcciones recientes.

## 6. Reportes proactivos
- **Telegram (resumen rápido):** semanal = últimos 7 días; mensual = ciclo recién cerrado.
  Redactado por Groq con fallback a texto.
- **Correo (detallado, solo mensual):** HTML vía Resend (`_html_reporte_mensual`): total, barras por
  categoría con Δ, top gastos (fecha estilizada `18 de mayo, 2026`), MSI activos, y una sección de
  recomendaciones generada por Groq.
- **Disparo:** `/reporte [mensual]` (a quien lo pide; el mensual además manda el correo) o
  `GET /reporte?secret=<SHORTCUT_SECRET>&tipo=semanal|mensual` (a ambos usuarios).
- **Calendario en producción:** semanal lunes 9am, mensual día 5 — vía rutina externa que pega el endpoint.

## 7. Flujo de voz (cómo funciona hoy)
La voz **no es un camino aparte**: se transcribe y se reusa todo el cerebro del texto.
1. `handle_voice` es entry-point de `conv_gasto` para `filters.VOICE | filters.AUDIO`.
2. Descarga el audio de Telegram (`get_file` → `download_as_bytearray`).
3. `groq_transcribir` (Whisper `whisper-large-v3-turbo`, `language="es"`) → texto. Corre en
   `asyncio.to_thread` para no bloquear el event loop.
4. Muestra "🎤 Entendí: {texto}" como confirmación de lo que escuchó.
5. Pasa el texto a `_procesar_conversacion` → de ahí en adelante es idéntico a un mensaje escrito:
   puede terminar como **gasto, consulta o edición**.
- Requiere `GROQ_API_KEY`; si no está, avisa que necesita configurarla.
- Implicación: cualquier cosa que puedas hacer escribiendo, la puedes hacer hablando
  (registrar, preguntar, corregir).

## 8. Categorización automática y aprendizaje
- `inferir_categoria(concepto)` resuelve en orden: **reglas → aprendizaje → similitud (>80%) → Google Maps**.
- Lo aprendido se guarda en la BD Aprendizaje (con limpieza automática de entradas viejas de 1 solo uso).
- Conceptos únicos (Netflix, Spotify, Walmart…) NO se guardan en Aprendizaje.

---

## Comandos disponibles
| Comando | Qué hace |
|---------|----------|
| `/start` | Mensaje de bienvenida e instrucciones |
| `/resumen [MES]` | Resumen con tabla por categoría + **proyección de cierre** + **narrativa** del mes (Groq) |
| `/estadisticas` | Compara mes anterior vs mes activo |
| `/top [MES]` | Top 5 gastos más caros del mes |
| `/buscar <texto>` | Busca gastos por concepto (Notion `contains`), últimos 12, con suma |
| `/corregir` | Panel inline para editar un gasto reciente |
| `/eliminar` | Archiva el último gasto |
| `/reporte [mensual]` | Dispara el reporte semanal (o mensual + correo) |
| `/prueba` | Simula el parseo de un gasto sin guardarlo (muestra origen de la inferencia) |
| `/cancelar` | Cancela la acción en curso |

---

## Lógica de tarjetas y meses
| Tarjeta | Corte |
|---------|-------|
| BBVA05  | día ≥ 5 → mes+1 |
| BBVA12  | día ≥ 12 → mes+1 |
| HEYB25  | día ≥ 25 → mes+2, resto → mes+1 |
| BMEX04  | día ≥ 4 → mes+1 |
| EFVO    | mes actual |

- **Asignación automática** (si no se especifica tarjeta): días 5-11 → BBVA05, resto → BBVA12.
- **Mes activo** (para `/resumen`): si hoy ≥ día 5 → mes siguiente; si hoy < 5 → mes actual.
- **Ciclo de mes vs fecha real:** las consultas por "mes" usan la relación `Mes` (ciclo de
  facturación: ENE26, FEB26…). Las consultas por fecha exacta (ayer, rango) y las históricas usan
  directamente la propiedad `Fecha` de Notion, ignorando el ciclo.

---

## Formatos de mensaje y fecha
**Tarjeta de gasto:**
```
✅ Gasto guardado

📌 Starbucks
💵 $150.00
🗓️ 17/MAY/26
💳 BBVA05
🧾 JUN26
🏷️ Treat
🗂️ Diversión
🔗 Ver en Notion
```

**Resumen / estadísticas:** tabla monoespaciada dentro de code block (con línea vacía inicial para
que el botón `</>` de Telegram no tape la primera fila). Emojis estrechos (⛪) llevan espacio extra.

**Fechas (2 formatos):**
- `_fecha_compacta` → `18/MAY/26` (mes en MAYÚSCULA, `MESES_ESP`): estándar en TODOS los mensajes al
  usuario (tarjeta de gasto, ticket, panel `/corregir`, `/eliminar`, `/buscar`, datos de consulta).
- `_fecha_larga` → `18 de mayo, 2026` (`MESES_ESP_LARGO`): solo el correo mensual (tono editorial).

---

## Arquitectura del código (bot.py)

### Funciones clave
- `_procesar_conversacion(update, context, texto, uid)` — cerebro compartido de texto y voz.
- `clasificar_mensaje_groq(texto, ultimo, historial)` — clasifica intención
  (gasto / multi_gasto / consulta / edición / otro); recibe la memoria conversacional.
- `responder_consulta_groq(...)` — consultas NL en 2 pasos (plan → datos → redacción).
- `ejecutar_consulta_finanzas(plan)` — ÚNICA función que trae datos para consultas (rutas: histórico / fecha real / ciclo de mes).
- `_datos_consulta_especial(modo, plan)` — modos de agregación (ranking, tendencia, hormiga…).
- `aplicar_edicion_contextual(...)` — ÚNICA ruta de escritura para editar un gasto.
- `groq_transcribir(audio_bytes)` — voz → texto (Whisper).
- `analizar_ticket_groq(img)` — foto de ticket → datos + productos (Llama 4 Scout).
- `guardar_notion(gasto)` / `registrar_y_notificar(...)` / `registrar_via_shortcut(...)` — registro.
- `inferir_categoria(concepto)` — pipeline de categorización.
- `precargar_meses()` — carga la BD Balance al cache al arrancar (evita timeouts).
- `notificar_pareja(context, uid, texto)` — aviso al otro usuario (helper único).
- `_base_desde_notion(nid)` — relee un gasto vigente desde la BD principal (usa `SC_INV`/`PR_INV`).
- `_construir_gasto_desde_data(data, hoy)` — arma un gasto completo desde el JSON del LLM (single y multi).
- `_registrar_multiples(...)` — guarda una lista de gastos y manda confirmación agrupada.
- `calcular_proyeccion(...)` / `_dias_en_ciclo()` — proyección de cierre del ciclo en `/resumen`.
- `generar_narrativa_resumen(...)` — 2-3 líneas de insight del mes (Groq).
- `verificar_hormiga(...)` / `detectar_anomalia(...)` — alertas en background al registrar.
- `agregar_historial`/`obtener_historial`/`limpiar_historial` — memoria conversacional (RAM).
- `cargar_historial_compartido()` — últimos MAX_HISTORIAL gastos de ambos usuarios (sin filtro UsuarioID); usado por `/corregir`.
- `cargar_historial_notion(uid)` — últimos MAX_HISTORIAL gastos de un usuario; usado por `/eliminar`.
- `guardar_meta(uid, presupuesto, limite, ciclo)` — upsert en Metas Bot (busca y reemplaza si ya existe).
- `cargar_meta(uid, presupuesto, ciclo)` — lee un límite específico; None si no existe.
- `cargar_metas_ciclo(uid, ciclo)` — todas las metas del usuario para un ciclo.
- `enviar_propuesta_mes(datos)` — corrutina async; envía el mensaje de apertura de ciclo con botones a ambos usuarios.
- `callback_propuesta` — maneja `^propuesta_`: confirma/salta meta, muestra desglose.

### ConversationHandlers (el orden de registro importa)
1. `conv_prueba` — `/prueba`
2. `conv_foto` — `filters.PHOTO` ← debe ir ANTES que conv_gasto
3. `conv_corregir` — `/corregir`; estado `CORREGIR_PANEL` maneja
   CallbackQuery `^edit:` (botones del panel) y texto (valor de campo o frase híbrida)
4. `conv_eliminar` — `/eliminar`
5. `conv_gasto` — `filters.TEXT` + `filters.VOICE | filters.AUDIO` (voz)

### Estados de conversación
```python
CONFIRMAR_MONTO  = 1   # monto >= 5000 (botones inline ^monto_)
CONFIRMAR_CAT    = 2   # concepto desconocido
CONFIRMAR_SUBCAT = 3   # subcategoría cuando el grupo tiene varias
CORREGIR_ELEGIR  = 10
CORREGIR_PANEL   = 11  # panel inline multi-campo (botones ^edit: + texto híbrido)
PRUEBA_GASTO     = 20
FOTO_CONFIRMAR   = 30
ELIMINAR_CONFIRM = 50
PROPUESTA_META   = 60  # reservado para ajuste de meta en apertura de ciclo (Feature 3)
```

### Endpoints HTTP
- `GET /` — health check (UptimeRobot)
- `POST /webhook` — updates de Telegram
- `POST /log` — gastos del iOS Shortcut/Siri (`{text, user_id, secret}`)
- `GET /reporte?secret=<SHORTCUT_SECRET>&tipo=semanal|mensual` — dispara el reporte a ambos usuarios
- `POST /propuesta_mes` — recibe datos de la rutina "Nuevo mes" y envía mensaje de apertura de ciclo con botones inline (`{secret, ciclo_nuevo, ciclo_anterior, total_anterior, promedio_3m, delta_pct, recurrentes_registrados, recurrentes_total, limite_propuesto, desglose}`)

---

## Notas técnicas críticas
1. **`precargar_meses()`** se llama en `main()` antes de `app.initialize()`; el cache evita timeouts de Notion.
2. **Loop async:** `app.update_processor._loop = loop` permite que `/log` despache corrutinas desde el thread del HTTP server.
3. **Historial en Notion, no en RAM:** persiste entre reinicios de Render.
4. **El Historial Bot puede quedar viejo:** al editar un gasto solo se actualiza la BD principal, no el snapshot del Historial. Por eso `/corregir` y `/eliminar` releen con `_base_desde_notion`.
5. **parse_mode="Markdown":** úsalo cuando el mensaje incluya el deep link o negritas. El panel de `/corregir` va en texto plano a propósito (conceptos con `*`/`_` romperían Markdown).
6. **conv_foto antes que conv_gasto:** si se invierte, las fotos caen en el handler de texto.
7. **IDs de relación Notion:** llegan con guiones — `.replace("-", "")` antes de comparar con `SC`/`PR`.
8. **Emojis estrechos** (⛪) necesitan un espacio extra para alinear las tablas monoespaciadas (`EMOJI_ESTRECHO`).
9. **Vision API:** requiere `GOOGLE_VISION_API_KEY`, Cloud Vision habilitada y la key sin restricciones (o con Vision en la lista).
10. **Fallback silencioso:** sin `GROQ_API_KEY` o ante cualquier fallo de IA, el bot usa el parser clásico. Cero regresiones.

---

## Deploy — procedimiento obligatorio
1. **Antes de cada deploy:** abrir en el browser
   `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Subir archivos a GitHub **arrastrando** (nunca copy-paste — evita comillas tipográficas).
3. Render → Manual Deploy → Restart service.

---

## Features en construcción / pendientes 🔲

### Feature 2 — Memoria semántica (Alias Bot) 🔲
El bot aprende alias personales de la conversación normal. Si el usuario dice
"recuerda que el café de siempre es Starbucks BBVA05", Groq detecta el patrón,
llama a `guardar_alias(uid, trigger, resolved)` y la próxima vez expande el texto
antes de clasificar (`expandir_aliases(uid, texto)`).
- BD: Alias Bot (personal, no compartida entre usuarios)
- Aprendizaje: detección automática en `clasificar_mensaje_groq`
- Expansión: antes de `clasificar_mensaje_groq` en `_procesar_conversacion`

### Feature 3 — Metas de gasto (Metas Bot) 🔲
El usuario fija metas por ciclo y presupuesto en lenguaje natural.
"Quiero gastar máximo $10,000 en Diversión este ciclo" → Groq detecta intent `meta`,
llama a `guardar_meta(uid, presupuesto, limite, ciclo)`.
- Alertas: al 80% y al 100% del límite, tras cada registro (`verificar_metas` en background)
- Progreso en `/resumen`: muestra meta y % usado si existe meta para ese ciclo
- BD: Metas Bot (personal, presupuesto TOTAL para meta global)

### Feature 4 — Multi-agente apertura de ciclo ✅ IMPLEMENTADO
La rutina "Nuevo mes [Notion]" (v7) ahora:
1. Registra todos los recurrentes en Notion (igual que antes)
2. Calcula total del ciclo anterior + promedio 3 meses
3. POST a `/propuesta_mes` → bot envía mensaje a ambos usuarios con:
   - Resumen del ciclo cerrado ($X, Δ% vs promedio)
   - Recurrentes registrados y su total
   - Meta sugerida para el nuevo ciclo
   - Botones: ✅ Meta $XX,XXX · ❌ Sin meta · 📋 Ver desglose
4. `callback_propuesta` guarda la meta confirmada en Metas Bot (presupuesto="TOTAL")

### Email BBVA (reconciliación automática) 🔲 v2
Conectar Gmail API, parsear PDF del estado de cuenta y cruzar con Notion.
Alta complejidad — pendiente para versión futura.

---

## Comandos BotFather
```
start        - 👋 Ver instrucciones
resumen      - 📊 Resumen del mes activo
estadisticas - 📈 Comparar este mes vs el anterior
reporte      - 📰 Reporte semanal (o /reporte mensual)
top          - 🏆 Top 5 gastos del mes
buscar       - 🔍 Buscar gastos por concepto
corregir     - ✏️ Corregir un gasto reciente
eliminar     - 🗑️ Eliminar el último gasto
prueba       - 🧪 Simular un gasto sin registrar
cancelar     - ❌ Cancelar acción en curso
```
