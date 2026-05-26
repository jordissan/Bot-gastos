# Bot Gastos — Contexto para Claude Code

> Documento de estado actual del bot (no es un changelog). Describe **lo que el bot hace hoy**
> y cómo está construido. Versión: **26.2.0**

> **Esquema de versiones** — `MAJOR.MINOR.PATCH`
> - **MAJOR**: feature set nuevo o cambio de dominio (nueva BD, nueva modalidad, capacidad estructural nueva). Ej: APScheduler, voz, metas.
> - **MINOR**: feature individual dentro de un dominio existente. Ej: nuevo modo de consulta, nueva alerta.
> - **PATCH**: fix, ajuste visual o actualización de docs.

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
- **Base de datos:** Notion API (6 bases: Gastos, Aprendizaje, Historial, Balance, Metas Bot, Alias Bot)
- **IA (Groq):** Llama 3.3 70B (texto), Llama 4 Scout (visión/tickets), Whisper large-v3-turbo (voz)
- **Otras APIs:** Google Maps Places (categorización), Google Vision (OCR de respaldo), Resend (correo)
- **Scheduler:** APScheduler==3.10.4 (`AsyncIOScheduler`) — reportes autoagendados dentro del bot
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

Cada gasto/edición que hace uno se le notifica al otro. **Las finanzas son conjuntas** — no hay separación de gastos por usuario en las consultas (todo se consulta como unidad familiar).

## Bases de datos Notion
| BD              | ID                                   | Propósito                            |
|-----------------|--------------------------------------|--------------------------------------|
| Gastos          | `9c66972a98e74d5b80df8a7e6569e3ca`  | Registro principal (fuente de verdad)|
| Aprendizaje Bot | `3ba6f37c717948a1a6aeac3b384ff33c`  | Diccionario de categorías aprendidas |
| Historial Bot   | `35f7eb0cbb9280ae8f02f69b4f242298`  | Últimos 5 gastos por usuario (snapshot) + filas `MEM_{uid}` (UsuarioID=0) para memoria persistente |
| Balance         | via `NOTION_BALANCE_ID` env var      | Meses dinámicos (ENE26, FEB26…) + rollups |
| Metas Bot       | `cf7906bcccfd4690b7ef8c1e996a8e17`  | Metas de gasto por ciclo y presupuesto (por usuario). Presupuesto="INGRESO" = ingreso estimado del ciclo |
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
   (Llama 3.3 70B) clasifica la intención en **gasto / multi_gasto / consulta / edición / meta / ingreso / alias / otro**.
2. Según la intención:
   - **consulta** → `responder_consulta_groq` (ver §3).
   - **edición** → `aplicar_edicion_contextual` sobre el último gasto (ver §5).
   - **gasto** → se registra.
   - **meta** → `guardar_meta(uid, presupuesto, limite, ciclo)`.
   - **ingreso** → `guardar_meta(uid, "INGRESO", monto, ciclo)` + muestra posición financiera inmediata.
   - **alias** → `guardar_alias(uid, trigger, resolved)`.
   - **otro** (saludo, charla) → responde "🤔 No entendí…" y termina.
3. Si Groq no aplica (formato estricto o sin API), usa el parser clásico `parsear_mensaje`.

**`_parece_gasto_estricto`:** devuelve `True` (salta Groq) solo si el mensaje tiene **≤ 9 tokens**
y alguno de los últimos 3 es un número.

**Memoria conversacional persistente** (`_memoria_ram` + Notion):
- **RAM**: cache activo por sesión — `turns` (últimos 8), `last_results`, `last_query`, `last_gasto`.
- **Notion**: dos filas en **Historial Bot** (`MEM_8663298433` y `MEM_8093171397`, UsuarioID=0) almacenan el JSON en el campo `NotionID`. Sobrevive reinicios de Render.
- `mem_cargar(uid)`: cold-start, carga Notion → RAM una sola vez por sesión.
- `mem_guardar(uid)`: persiste RAM → Notion en background tras cada acción relevante. TTL de 2h para `last_results`.
- `_manejar_referencia()`: intercepta antes de Groq mensajes como "dame el link", "elimínalo", "el más caro" y los resuelve contra el contexto en memoria.
- `ejecutar_consulta_finanzas` devuelve `gastos_raw` (con notion_ids) que se guarda en `last_results`.
- **Plan carryover**: el planner recibe los filtros del plan anterior (`last_query`) para resolver referencias como "¿y la semana pasada?", "¿y en esa subcategoría?".

## 3. Consultas en lenguaje natural (Hub Financiero)
Flujo de 2 pasos que evita que el LLM invente cifras:
1. Groq genera un **plan de consulta** (JSON): `{modo, meses, categoria, subcategoria, tarjeta, comercio, fecha_desde, fecha_hasta, anio, historico}`.
2. `ejecutar_consulta_finanzas` / `_datos_consulta_especial` traen los datos **de forma determinística** de Notion.
3. Groq **redacta** la respuesta solo con esos datos reales.

**Filtros disponibles en cualquier modo:**
- `categoria` — bolsa de presupuesto (Despensa, Restaurantes, Automovil…)
- `subcategoria` — tipo específico de gasto (Abarrotes, Gasolina, Treat…). NOTA: "Restaurantes" es tanto subcategoría como categoría — el planner usa `subcategoria` por defecto cuando hay ambigüedad.
- `tarjeta` — BBVA05 / BBVA12 / HEYB25 / BMEX04 / EFVO
- `comercio` — búsqueda de texto en concepto
- `fecha_desde` / `fecha_hasta` — rango de fecha exacta
- `meses` — códigos de ciclo (JUN26, MAY26…)
- `historico: true` — toda la historia desde 2020

**Tipos de pregunta que responde** (cada uno = un `modo` interno):
| Pregunta de ejemplo | modo |
|---------------------|------|
| "¿cuánto gasté ayer / la semana pasada?" | `detalle` + `fecha_desde/hasta` |
| "¿cuánto gasté este mes en Abarrotes?" | `detalle` + `subcategoria` |
| "¿cuánto gasté con BBVA12 este mes?" | `detalle` + `tarjeta` |
| "¿cuánto gasté con HEYB25 en Gasolina?" | `detalle` + `tarjeta` + `subcategoria` |
| "¿cuánto llevo pagado del Polo / en total?" | `historico: true` |
| "¿qué año gasté más?" | `por_anio` |
| "el gasto más antiguo / más caro" | `primero` / `mayor` |
| "¿en qué se me va el dinero?" | `ranking_categorias` |
| "¿dónde compro más seguido?" | `ranking_frecuencia` |
| "¿cuánto gasto al mes / al día en promedio?" | `promedio_mensual` / `promedio_dia` |
| "¿gasto más entre semana o en fin?" | `dia_semana` |
| "¿qué día del mes gasto más?" | `dia_mas_caro` |
| "¿cómo se reparte mi gasto por semana del mes?" | `semana_mes` |
| "¿voy por encima de mi promedio este mes?" | `desviacion` |
| "¿está subiendo mi gasto en Abarrotes?" | `tendencia` + `subcategoria` |
| "¿qué mes de 2025 fue el más caro?" | `mes_mas_caro` |
| "¿cuáles son mis gastos fijos?" | `recurrentes` |
| "¿cuánto llevo sin gastar en X?" | `dias_sin_gasto` |
| "¿cuál es mi gasto hormiga?" | `hormiga` |
| "¿cuándo fui por última vez a Costco?" | `ultima_visita` |
| "¿cuánto ahorraría si dejo Starbucks?" | `proyeccion_ahorro` |
| "¿qué MSIs tengo activos? ¿cuánto debo?" | `msi_tracker` |
| "¿dónde puedo ahorrar? ¿en qué gasto de más?" | `oportunidades_ahorro` |
| "¿cómo voy este mes? ¿cuánto me queda?" | `posicion_financiera` |
| "¿cuánto hemos ganado vs gastado históricamente?" | `tendencia_ingresos` |

- Consulta **histórica** (`historico: true`): avisa "🔍 Buscando en toda la historia…" porque
  puede tardar 15-30 s; agrega por año.
- Respaldo de presupuesto: si un gasto no tiene relación `Presupuesto`, el bot deriva la categoría
  desde la `Subcategoria` (`SUBCAT_PRESUPUESTO`).

## 4. Ingresos estimados (finanzas freelance)
Jordi y Nane son freelancers con ingresos variables. El bot maneja esto con **ingresos estimados por ciclo**:
- **Declarar:** "Este mes esperamos ganar $45,000" → se guarda en Metas Bot con `presupuesto="INGRESO"`.
- **Actualizar:** en cualquier momento con el mismo mensaje.
- **Consultar posición:** "¿Cómo voy este mes?" → `posicion_financiera` — muestra gastado/estimado, saldo libre, proyección de ahorro.
- **Historial:** "¿Cuánto hemos ganado vs gastado?" → `tendencia_ingresos` — últimos 6 ciclos.
- El ingreso es compartido (finanzas conjuntas); cualquier usuario puede declararlo.
- Si no hay ingreso declarado, las consultas de posición financiera lo indican y piden declararlo.

## 5. MSI Tracker
Los MSIs se registran con formato `"Concepto X/Total"` (ej. "MacBook Pro 4/18").
- `msi_tracker` detecta todos los MSIs históricos vía subcategoría=MSI, encuentra el pago más reciente de cada uno, y calcula restantes y compromiso mensual total.
- El correo mensual ya incluía los MSIs del ciclo cerrado; `msi_tracker` es la versión conversacional en tiempo real.

## 6. Tickets por foto (OCR)
- La foto va directo a Llama 4 Scout (`analizar_ticket_groq`): extrae **comercio, monto, fecha y la
  lista de productos** `[{nombre, precio}]`.
- El desglose se guarda como **tabla Notion** (Producto | Precio) dentro de la página del gasto.
- **Si el ticket tiene productos, el concepto lleva `*` al final** (ej. `Walmart*`) como señal visual.
- Preview con botones **Confirmar / Cancelar** antes de guardar.
- Fallback a Google Vision (`ocr_ticket` + `parsear_ticket`) si Groq falla.

## 7. Editar y borrar
- **`/corregir` — panel inline multi-campo (híbrido):** muestra los **últimos 5 gastos de ambos
  usuarios combinados** para que cualquiera pueda corregir el gasto del otro. Eliges el número (1-5)
  y se abre un panel con teclado en línea y los 6 campos editables: **monto, fecha, tarjeta,
  categoría, presupuesto, concepto**. Apilas varios cambios y se aplican **todos en un solo PATCH**.
  También acepta frases ("monto 95 y tarjeta BBVA05").
- **Edición contextual por frase:** justo después de registrar, "cámbialo a 400", "ponlo en
  restaurantes" editan el último gasto (guardado en RAM).
- Ambas rutas usan la **única** función de escritura `aplicar_edicion_contextual`.
- **`/eliminar`:** archiva el último gasto en Notion (pide confirmación).

## 8. Reportes proactivos
- **Telegram (resumen rápido):** semanal = últimos 7 días; mensual = ciclo recién cerrado.
  Incluye **desglose por tarjeta** en el texto del reporte.
  Redactado por Groq con fallback a texto.
- **Correo (detallado, solo mensual):** HTML vía Resend: total, barras por categoría con Δ, top gastos, MSI activos, recomendaciones.
- **Disparo:** `/reporte [mensual]` o `GET /reporte?secret=<SHORTCUT_SECRET>&tipo=semanal|mensual`.
- **Calendario:** semanal lunes 9am MX (`job_reporte_semanal`), mensual día 5 2pm MX (`job_reporte_mensual`) — APScheduler dentro del bot.

## 9. Flujo de voz
La voz **no es un camino aparte**: se transcribe y se reusan todos los flujos de texto.
- Whisper `whisper-large-v3-turbo` → texto → `_procesar_conversacion`.
- Cualquier cosa que puedas hacer escribiendo, la puedes hacer hablando (registrar, preguntar, corregir, declarar ingreso).

## 10. Categorización automática y aprendizaje
- `inferir_categoria(concepto)` resuelve en orden: **reglas → aprendizaje → similitud (>80%) → Google Maps**.
- Lo aprendido se guarda en la BD Aprendizaje (con limpieza automática de entradas viejas de 1 solo uso).

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
| `/prueba` | Simula el parseo de un gasto sin guardarlo |
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

**Fechas (2 formatos):**
- `_fecha_compacta` → `18/MAY/26`: estándar en todos los mensajes al usuario.
- `_fecha_larga` → `18 de mayo, 2026`: solo el correo mensual.

---

## Arquitectura del código (bot.py)

### Funciones clave
- `_procesar_conversacion(update, context, texto, uid)` — cerebro compartido de texto y voz.
- `clasificar_mensaje_groq(texto, ultimo, historial)` — clasifica intención
  (gasto / multi_gasto / consulta / edición / meta / **ingreso** / alias / otro).
- `responder_consulta_groq(...)` — consultas NL en 2 pasos (plan → datos → redacción). El plan JSON ahora incluye `subcategoria`, `tarjeta`; el contexto incluye `last_query` para carryover de filtros.
- `ejecutar_consulta_finanzas(plan)` — ÚNICA función que trae datos para consultas. Filtros: categoria, **subcategoria** (via SC dict), **tarjeta** (rich_text), comercio, fecha, historico.
- `_datos_consulta_especial(modo, plan)` — modos de agregación. Todos los modos propagan `subcategoria_id`. Nuevos modos: **msi_tracker**, **oportunidades_ahorro**, **posicion_financiera**, **tendencia_ingresos**.
- `_gastos_recientes(n, categoria, meses, subcategoria_id)` — lista de gastos recientes; soporta filtro de subcategoría.
- `_agg_ciclo(mes)` — agrega gastos de un ciclo; ahora incluye `por_tarjeta`.
- `aplicar_edicion_contextual(...)` — ÚNICA ruta de escritura para editar un gasto.
- `guardar_meta(uid, presupuesto, limite, ciclo)` — upsert en Metas Bot. `presupuesto="INGRESO"` para guardar ingreso estimado.
- `cargar_meta(uid, presupuesto, ciclo)` — lee un límite o ingreso específico.
- `mem_cargar(uid)` / `mem_guardar(uid)` — memoria persistente Notion.
- `_manejar_referencia()` — intercepta referencias contextuales antes de Groq.
- `enviar_reporte(tipo)` — reporte a Telegram; incluye desglose por tarjeta.

### ConversationHandlers (el orden de registro importa)
1. `conv_prueba` — `/prueba`
2. `conv_foto` — `filters.PHOTO` ← debe ir ANTES que conv_gasto
3. `conv_corregir` — `/corregir`
4. `conv_eliminar` — `/eliminar`
5. `conv_gasto` — `filters.TEXT` + `filters.VOICE | filters.AUDIO`

### Endpoints HTTP
- `GET /` — health check (UptimeRobot)
- `POST /webhook` — updates de Telegram
- `POST /log` — gastos del iOS Shortcut/Siri
- `GET /reporte?secret=<SHORTCUT_SECRET>&tipo=semanal|mensual` — dispara reporte a ambos usuarios
- `POST /propuesta_mes` — apertura de ciclo con botones inline

---

## Notas técnicas críticas
1. **IDs de relación Notion:** llegan con guiones — `.replace("-", "")` antes de comparar con `SC`/`PR`.
2. **Tarjeta en Notion:** campo `rich_text` (no select) — leer con `props.get("Tarjeta", {}).get("rich_text", [])`.
3. **Subcategoría y Presupuesto:** "Restaurantes" existe en ambos dicts (SC y PR). El planner usa `subcategoria` por default cuando hay ambigüedad.
4. **Ingreso estimado:** se guarda en Metas Bot con `presupuesto="INGRESO"`. `cargar_meta(uid, "INGRESO", ciclo)` lo lee; se busca en ambos UIDs porque las finanzas son conjuntas.
5. **MSI formato:** `"Concepto X/Total"` — ej. "MacBook Pro 4/18". `msi_tracker` usa regex `^(.+?)\s+(\d{1,2})\s*/\s*(\d{1,2})\s*$`.
6. **gastos_raw:** máximo 20 gastos ordenados por monto (era 10 antes).
7. **parse_mode="Markdown":** úsalo cuando el mensaje incluya el deep link o negritas.
8. **conv_foto antes que conv_gasto:** si se invierte, las fotos caen en el handler de texto.
9. **Fallback silencioso:** sin `GROQ_API_KEY` o ante cualquier fallo de IA, el bot usa el parser clásico.

---

## Deploy — procedimiento obligatorio
1. **Antes de cada deploy:** abrir en el browser
   `https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true`
2. Subir archivos a GitHub **arrastrando** (nunca copy-paste — evita comillas tipográficas).
3. Render → Manual Deploy → Restart service.

---

## Features en construcción / pendientes 🔲

### Feature 2 — Memoria semántica (Alias Bot) ✅ IMPLEMENTADO
El bot aprende alias personales de la conversación normal.
- BD: Alias Bot (personal, no compartida entre usuarios)
- Detección automática en `clasificar_mensaje_groq`
- Expansión antes de `clasificar_mensaje_groq` en `_procesar_conversacion`

### Feature 3 — Metas de gasto (Metas Bot) ✅ IMPLEMENTADO
El usuario fija metas por ciclo y presupuesto en lenguaje natural.
- Alertas al 80% y al 100% del límite, tras cada registro
- Progreso en `/resumen`
- BD: Metas Bot (presupuesto TOTAL para meta global)

### Feature 4 — Multi-agente apertura de ciclo ✅ IMPLEMENTADO (bot-side)
Endpoint `POST /propuesta_mes` listo. La rutina "Nuevo mes" fue simplificada — solo
registra recurrentes en Notion sin notificar al bot.

### Feature 5 — Hub Financiero v2 ✅ IMPLEMENTADO
- Filtro por subcategoría en todos los modos (incluyendo tendencia, desviación, hormiga, etc.)
- Filtro por tarjeta (BBVA05/12/HEYB25/BMEX04/EFVO) en cualquier consulta
- Plan carryover: el bot recuerda los filtros de la consulta anterior
- Ingresos estimados (freelance-friendly) guardados en Metas Bot
- MSI tracker conversacional
- Análisis de oportunidades de ahorro vs histórico
- Posición financiera en tiempo real (ingreso estimado vs gasto real)
- Tendencia histórica de ingresos vs gastos
- Desglose por tarjeta en reportes semanal y mensual

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
buscar       - 🔍 Buscar gasto
corregir     - ✏️ Corregir un gasto reciente
eliminar     - 🗑️ Eliminar el último gasto
prueba       - 🧪 Simular un gasto
cancelar     - ❌ Cancelar acción en curso
```
