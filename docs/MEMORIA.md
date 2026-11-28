# memoria.md — Memoria institucional del proyecto

> Acumula decisiones de diseño, conceptos clave del dominio y lecciones aprendidas.
> **Nunca se borra** — se agrega al inicio de cada entrada nueva.
> Para el estado operativo de la última sesión, ver `handoff.md`.
>
> **Actualizar al cierre de sesión** cuando: se tomó una decisión de diseño, se aclaró
> un concepto del dominio, se descartó algo con razonamiento, o se aprendió una lección
> que evita repetir un error. No esperar a que Jordi lo pida.

---

## 2026-11-28 — Comandos en lenguaje natural (v28.7.0)

**Pedido de Jordi:** por voz dijo «corre una prueba» y el bot respondió «No entendí». Decir o escribir el comando en palabras debe ser igual que usar la diagonal.
**Decisión:** detector determinístico primero (regex sobre el texto sin acentos) y la intención `comando` de Groq como respaldo. El detector no gasta llamadas a Groq y es predecible; es conservador a propósito: un número de 2+ dígitos lo anula, para que «pagué 350 de una prueba» siga siendo gasto. «Elimina el gasto de Uber» no es comando (no sabemos cuál); va a Groq.
**Lección:** un comando en palabras llega por `conv_gasto`, así que `conv_prueba`/`conv_corregir` no se enteran. Se fija su estado a mano con la API interna de PTB 21; si PTB cambia, solo se pierde el estado (queda en el log) y la diagonal sigue funcionando. De paso: los botones «Sí, eliminar» de «bórralo» no tenían handler fuera de `/eliminar`; ahora hay uno global.

---

## 2026-11-28 — Listados de gastos como tabla alineada (v28.6.0)

**Pedido de Jordi:** la respuesta a «¿cómo vamos en ENE27?» se veía desordenada: renglones «• Comercio $monto · DD/NOV/26» que se partían en el iPhone y no alineaban. Además decía «12 gastos» y solo listaba 8.
**Causa:** el LLM redactaba la lista a partir de `res["top"]`, que estaba recortado a 8; y el ancho del renglón dependía del nombre del comercio.
**Decisión:** la lista la pinta el código, no el LLM: bloque monoespaciado (`<pre>`) de ≤30 columnas con fecha corta (26/NOV), concepto recortado con «…» y monto alineado a la derecha, más total. Hasta 20 gastos; si hay más, «… y N más». El LLM solo agrega 1–2 frases. Se descartó la cita desplegable (como el desglose de tickets) porque no alinea columnas y esconde lo que preguntaste. Mismo formato en `/top`, `/buscar` y el preview de acciones masivas.
**Lección:** todo lo que deba verse ordenado o completo (listas, conteos) se arma en código; el LLM solo comenta.

---

## 2026-11-28 — Texto con gpt-oss-120b; Llama y Muse fuera de alcance

**Revisión del catálogo de Groq (28-nov-2026):** en el plan gratis/Developer solo quedan `openai/gpt-oss-20b` y `openai/gpt-oss-120b` para texto, `qwen/qwen3.8-27b` como único modelo con visión y `whisper-large-v3(-turbo)` para voz. Llama 3.1/3.3 y Meta `muse-spark-open` están en el catálogo pero solo para Enterprise; Llama 4 ya no aparece. Ninguno de los modelos del bot tiene retiro anunciado.
**Decisión (Jordi):** texto pasa a `gpt-oss-120b` (mejor razonamiento y redacción en español, mismo límite de 1,000 llamadas/día, ~500 t/s contra ~1,000 del 20b). Visión y voz se quedan. Si se siente lento, poner `GROQ_MODELO_TEXTO=openai/gpt-oss-20b` en Render, sin re-deploy.
**De paso:** el bot llamaba «Nani» a Nane en `USUARIOS_NOMBRES` y en los prompts; corregido.

---

## 2026-11-28 — Desglose del ticket dentro de Telegram

**Pedido de Jordi:** ver el desglose rápido en Telegram, sin ir a Notion ni recibir otro mensaje largo, y poder cerrarlo.
**Decisión:** usar la cita desplegable nativa de Telegram (`<blockquote expandable>`, Bot API 7.4) en HTML. Se descartaron un mensaje aparte (ensucia el chat con tickets largos) y un botón «Ver desglose» (requiere guardar los productos y otro callback). Solo el flujo de fotos usa HTML (`msg_gasto_html`); el resto sigue con `msg_gasto` en Markdown.

---

## 2026-11-28 — Fotos de tickets de vuelta; el bot vuelve al uso diario

**Hallazgo:** las fotos fallaban por dos cosas a la vez: Groq retiró `qwen/qwen3.6-27b` (404) y el respaldo de Google Vision da 403 (llave sin permiso para Vision).
**Cómo se resolvió:** `/diagnostico` (v28.3.3) mostró el catálogo vivo de Groq; el único modelo de visión era `qwen/qwen3.8-27b`. Jordi agregó `GROQ_MODELO_VISION` en Render y quedó en verde sin tocar código. v28.4.2 cambia el default en `config.py` al mismo modelo (reemplaza al PR #3).
**Lección:** cuando Groq retira un modelo, el arreglo rápido es la variable de entorno guiada por `/diagnostico`; el código se alinea después. Desde el 28-nov-2026 Jordi y Nane retoman el bot para las finanzas del hogar: priorizar que registrar y leer tickets nunca se caiga.
**Pendiente:** el log de Render imprime la URL de Telegram con el token (logger `httpx` en INFO); conviene bajarlo a WARNING.

---

## 2026-11-25 (tarde) — Presupuestos que no sumaban

**Hallazgo:** `PR` mandaba gastos a Generosidad, Iglesia y Departamento, páginas que no están en la BD Presupuestos: se guardaban pero no sumaban en ningún presupuesto (Ikea, Home Depot, Amazon, ofrendas…). Impuestos tenía un ID con una letra mal.
**Decisión de Jordi:** Diezmo y Ofrenda → Diezmo; Regalos → Personal; Muebles y Decoración → Personal; Mercado y Comida siguen juntas en Abarrotes.
**Cómo:** el presupuesto ahora sale de `SUBCAT_PRESUPUESTO` aunque el menú agrupe distinto (los grupos del menú son solo UI). Al guardar, si el presupuesto aprendido no existe en `PR`, se deriva de la subcategoría. Un test verifica que todo destino exista en `PR`.

---

## 2026-11-25 (tarde) — Tarjeta por defecto según el día de corte

**Decisión de Jordi:** sin tarjeta explícita se usa la tarjeta que acaba de cortar: días 5–11 → BBVA05, 12–24 → BBVA12, 25 al 4 → HEYB25. Sustituye a «HEYB25 cualquier día» de la mañana. La regla vive en `config.TARJETA_DEFAULT_POR_DIA`.
**Interpretación:** Jordi dijo «HEYB25 si es día 25, BBVA05 si es día 5 y BBVA12 si es día 12»; se leyó como rangos desde cada corte hasta el siguiente. Los días 1–4 quedan en HEYB25 porque BMEX04 (corte 4) está pendiente.
**Pendiente:** cómo entra Banamex Joy (BMEX04); Jordi tiene una idea.
**Sin cambio:** el ciclo activo sigue anclado en el día 25 (`DIA_INICIO_CICLO`).

---

## 2026-11-25 — Tarjeta por defecto HEYB25 y ciclo activo desde el día 25

**Decisión de Jordi:** sin tarjeta explícita, el gasto va a **HEYB25** (antes: BBVA05 días 5–11, BBVA12 el resto). El **ciclo activo** arranca el **día 25** (corte de HEYB25), no el 5: hoy ≥ 25 → mes+2, hoy < 25 → mes+1. `mes_activo_str()` ahora es literalmente `calcular_mes(hoy, "HEYB25")`, así que ambas reglas no pueden divergir. El reporte mensual se movió al día 25 para coincidir con el cierre.
**Historia:** Jordi recuerda que el ancla había sido 25 antes de pasar a 5. El repo no lo muestra: el día 5 ya estaba en el primer commit (268888c, 25-may-2026), así que el cambio fue antes de subirlo a GitHub.
**Descartado:** la lógica de pagar unas tarjetas el 15 y otras el 30 (sus ingresos ya no caen en esas fechas).

---

## Conceptos del dominio — verdades permanentes

### Ciclo de pago vs mes calendario
`JUN26` en Notion = **"gastos que se pagan en junio 2026"** (mes de pago), NO "gastos comprados en junio".
Una compra del 26 de junio queda en:
- **EFVO** → JUN26 (siempre mes actual)
- **BBVA05** → JUL26 (corte día 5, 26 ≥ 5)
- **BBVA12** → JUL26 (corte día 12, 26 ≥ 12)
- **BMEX04** → JUL26 (corte día 4, 26 ≥ 4)
- **HEYB25** → AGO26 (corte día 25, 26 ≥ 25 → mes+2)

Cuando el usuario dice "dame los gastos de JUN26", quiere exactamente `Mes = JUN26` en Notion — filtrado por subcategoría o lo que pida. Es determinístico, no ambiguo. Si no hay resultados, decirlo claro.

### Finanzas conjuntas
Jordi y Nane manejan finanzas como unidad familiar. **Nunca separar gastos por usuario en consultas.** El ingreso estimado también es conjunto — se guarda y se lee en ambos UIDs.

### Subcategoría vs Categoría (presupuesto)
"Restaurantes" existe en SC (subcategoría) Y en PR (presupuesto). El planner debe usar `subcategoria=Restaurantes` por default cuando hay ambigüedad — es más preciso. **Nunca poner `subcategoria` y `categoria` simultáneamente en el plan.**

### Semántica de "JUN26" en consultas
El usuario entiende `JUN26` como ciclo de pago. Nunca intentar "ayudar" traduciendo automáticamente a fechas calendario — rompe la semántica del sistema. Si JUN26 está vacío en Notion, es porque los gastos de esas fechas quedaron en otro ciclo. El bot debe informarlo, no inventar.

---

## Decisiones de diseño

### Query en 2 pasos (plan → datos → redacción)
El LLM nunca toca los datos directamente — primero genera un plan JSON, luego `ejecutar_consulta_finanzas` hace la query determinística, y solo entonces el LLM redacta con esos datos. Esto elimina alucinaciones de cifras. Aprendido desde el inicio del Hub Financiero.

### `prompt_resp` con REGLA CRÍTICA
La instrucción débil "usa SOLO estos datos" no fue suficiente — Groq usaba el historial de la conversación cuando los datos estaban vacíos. Se cambió a una REGLA CRÍTICA explícita: "PROHIBIDO usar información de mensajes anteriores, inventar cifras o mencionar meses/gastos que no aparezcan en los datos." Si los datos están vacíos, el bot debe decirlo directamente.

### APScheduler dentro del bot (no rutinas externas)
Las rutinas remotas de Claude Code (CCR) no pueden hacer llamadas HTTP salientes desde el entorno de Render. Por eso los reportes se movieron a APScheduler dentro del propio bot. El bot ya corre 24/7 y tiene toda la lógica — es el lugar correcto.

### Ingreso estimado en Metas Bot con presupuesto="INGRESO"
Jordi y Nane son freelancers con ingresos variables. No hay forma de saber el ingreso real antes de que llegue. Se usa `guardar_meta(uid, "INGRESO", monto, ciclo)` para declarar el ingreso esperado. Metas Bot ya existía — se reusó con una clave especial en lugar de crear una nueva BD.

### Tarjeta como `rich_text` en Notion (no select)
El campo Tarjeta en Notion es `rich_text`, no `select`. Leer con `.get("Tarjeta", {}).get("rich_text", [])`. Confundir esto causa que el filtro de tarjeta no funcione silenciosamente.

### `conv_foto` antes que `conv_gasto`
Si se invierte el orden de registro de los ConversationHandlers, las fotos caen en el handler de texto y se rompe el OCR. El orden en `main()` es crítico.

---

## Cosas intentadas y descartadas — con razonamiento

### Auto-retry por mes calendario (descartado)
**Qué era:** cuando `Mes=JUN26` devolvía 0 resultados, se reintentaba la query con `fecha_desde/fecha_hasta` del mes calendario equivalente.
**Por qué se descartó:** el usuario aclaró que `JUN26` = ciclo de pago, no mes calendario. El auto-retry "ayudaba" de forma que contradecía la semántica del sistema. Si JUN26 está vacío, es la respuesta correcta.
**Qué quedó:** el helper `_ciclo_a_rango_calendario(ciclo)` se mantiene en el código — puede ser útil en el futuro para algo más explícito.

### Rutinas remotas CCR para reportes (reemplazadas)
**Qué era:** reportes semanal y mensual disparados desde rutinas de Claude Code remoto.
**Por qué se reemplazó:** las rutinas CCR no pueden hacer llamadas HTTP salientes desde Render. Los reportes nunca llegaban.
**Solución:** APScheduler dentro del bot (ver arriba).

### Rutina "Nuevo mes" con notificación al bot (simplificada)
**Qué era:** la rutina de Claude Code "Nuevo mes" terminaba con un POST al bot notificando el nuevo ciclo.
**Por qué se eliminó:** el endpoint `POST /propuesta_mes` existe en el bot, pero la notificación al bot no agrega valor — solo creaba una dependencia frágil. La rutina ahora solo crea recurrentes en Notion y termina.

---

## Backlog — features explorados, postergados indefinidamente

| Feature | Motivo de postergación |
|---------|------------------------|
| Reconciliación email BBVA (Gmail API + PDF) | Alta complejidad; requiere parsear PDFs de banco, cruzar con Notion. Versión futura. |
| Búsqueda híbrida ciclo+calendario | Evaluar si tiene sentido cuando la pregunta es genuinamente ambigua — pero NO como comportamiento default. |
