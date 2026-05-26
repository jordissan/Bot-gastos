# memoria.md — Contexto persistente de sesiones con Claude

> Leer este archivo al inicio de cada sesión antes de tocar bot.py o CLAUDE.md.
> Contiene decisiones tomadas, bugs resueltos, cosas descartadas y pendientes activos.
> Formato: entradas más recientes arriba.

---

## Sesión: 2026-05-20 / 2026-05-26 — Hub Financiero v2 + fixes críticos

### ¿Qué se hizo en esta sesión?

#### 1. Bug: subcategoría ignorada en consultas (RESUELTO ✅)
**Síntoma:** bot preguntado por "abarrotes" devolvía el total de "Despensa" (toda la categoría).
**Causa:** `ejecutar_consulta_finanzas` no filtraba por subcategoría — solo por categoría.
**Fix:** se añadió `subcategoria_id` derivado del dict `SC` y se filtra en los tres loops de la función. También se propagó a `_datos_consulta_especial` para que todos los modos especiales lo respeten.

#### 2. Feature: Hub Financiero v2 (IMPLEMENTADO ✅)
Se expandió masivamente el bot como hub financiero personal. Cambios en bot.py:
- **Filtro por subcategoría** en todos los modos de consulta (era solo global antes).
- **Filtro por tarjeta** (`tarjeta_filtro` vía campo `rich_text` Tarjeta en Notion) en cualquier consulta.
- **Plan carryover:** el planner recibe `last_query` de la memoria para resolver "¿y la semana pasada?", "¿y con BBVA12?".
- **Ingresos estimados freelance:** `guardar_meta(uid, "INGRESO", monto, ciclo)` en Metas Bot. El clasificador detecta frases como "este mes esperamos ganar $45,000". Muestra posición financiera inmediata al declarar.
- **MSI tracker** (`msi_tracker`): ve todos los MSIs activos (formato "Concepto X/Total"), calcula restantes y compromiso mensual.
- **Oportunidades de ahorro** (`oportunidades_ahorro`): compara últimos 3 meses vs promedio de 6 meses por categoría.
- **Posición financiera** (`posicion_financiera`): ingreso estimado vs gasto real, % gastado, saldo libre, proyección.
- **Tendencia ingresos** (`tendencia_ingresos`): historial 6 ciclos de ingreso declarado vs gasto real.
- **Desglose por tarjeta** en reportes semanal y mensual (campo `por_tarjeta` en `_agg_ciclo`).
- **`gastos_raw` limit:** aumentado de 10 → 20.

#### 3. Bug: Groq hallucina datos de turnos anteriores cuando resultado es vacío (RESUELTO ✅)
**Síntoma:** usuario preguntó "gastos de abarrotes de JUN26"; bot dijo "no tengo JUN26, solo MAY26" y luego listó los gastos de MAY26 inventándolos del historial de la conversación.
**Causa:** `prompt_resp` tenía instrucción débil "usa SOLO estos datos" pero Groq ignoraba eso y usaba el contexto de turnos anteriores cuando los datos estaban vacíos.
**Fix en `responder_consulta_groq`:** instrucción reforzada con "REGLA CRÍTICA: responde ÚNICAMENTE con los datos mostrados arriba. PROHIBIDO usar información de mensajes anteriores, inventar cifras o mencionar meses/gastos que no aparezcan en esos datos."

#### 4. Auto-retry calendario — IMPLEMENTADO Y LUEGO REVERTIDO ❌
**Lo que se hizo:** cuando el ciclo de pago devolvía 0 resultados, se reintentaba la query con `fecha_desde/fecha_hasta` del mes calendario.
**Por qué se revirtió:** el usuario aclaró que cuando dice "gastos de JUN26" quiere exactamente `Mes = JUN26` en Notion. Si no hay resultados, debe decirlo claramente — no buscar por fecha de compra. El auto-retry contradecía su intención.
**Lección:** no "ayudar de más" cuando el concepto de ciclo de pago está bien definido en Notion.

#### 5. APScheduler — reportes autoagendados (IMPLEMENTADO ✅, en sesión anterior)
Se movió el disparo de reportes del schedule externo de Claude (que no puede hacer HTTP saliente desde Render) al interior del propio bot con APScheduler.
- `job_reporte_semanal`: lunes 9am MX
- `job_reporte_mensual`: día 5 2pm MX
Ambos llaman la lógica interna directamente (sin HTTP self-call).

---

### Conceptos clave aclarados en esta sesión

#### Ciclo de pago vs mes calendario
`JUN26` en Notion = **"gastos que se pagan en junio 2026"** (mes de pago), NO "gastos comprados en junio".
- BBVA05 (corte día 5): compra 26-jun → JUL26
- BBVA12 (corte día 12): compra 26-jun → JUL26
- HEYB25 (corte día 25): compra 26-jun → AGO26 (mes+2)
- BMEX04 (corte día 4): compra 26-jun → JUL26
- EFVO: compra 26-jun → JUN26 (siempre mes actual)

**Cuando el usuario dice "gastos de JUN26" quiere `Mes = JUN26` en Notion, filtrado por subcategoría/categoría. No es ambiguo — el bot ya lo hace bien.**

#### Finanzas conjuntas Jordi + Nane
No hay separación de gastos por usuario en consultas. Todo es familia. El ingreso estimado es conjunto también (cualquier usuario puede declararlo, se lee de ambos UIDs).

#### Subcategoría vs Categoría (presupuesto)
- "Restaurantes" existe en AMBOS dicts (SC subcategoría y PR presupuesto). El planner usa `subcategoria=Restaurantes` por default cuando hay ambigüedad (más preciso).
- NUNCA poner `subcategoria` y `categoria` simultáneamente en el plan.

---

### Estado del repo al cierre de sesión
- **Branch:** main
- **Último commit:** `703d45d` — "revert: elimina auto-retry calendario"
- **Todos los cambios pusheados** a github.com/jordissan/Bot-gastos

### Deploy pendiente
⚠️ **Render → Manual Deploy → Restart service** — los cambios de esta sesión están en GitHub pero NO desplegados hasta que se haga el deploy manual.
Verificar en logs: `[APScheduler] Scheduler iniciado.`

---

### Pendientes / Ideas exploradas no implementadas

| Item | Estado | Notas |
|------|--------|-------|
| Email BBVA reconciliación (Gmail API + PDF) | 🔲 Pendiente | Alta complejidad, versión futura |
| Rutina "Nuevo mes" en Claude Code | ✅ Simplificada | Solo crea recurrentes en Notion, sin notificar al bot |
| Rutinas remotas de reportes en Claude Code | ❌ Eliminadas | Reemplazadas por APScheduler dentro del bot |
| Dashboard HTML | ✅ Existe | `/Users/jordi/Documents/Claude/Projects/Hub Financiero/dashboard.html` |

---

### Archivos relevantes del proyecto

| Archivo | Ruta |
|---------|------|
| Bot principal | `/Users/jordi/Bot-gastos/bot.py` |
| Contexto técnico | `/Users/jordi/Bot-gastos/CLAUDE.md` |
| Este archivo | `/Users/jordi/Bot-gastos/memoria.md` |
| Plan automatización (referencia) | `/Users/jordi/Documents/Claude/Projects/Hub Financiero/plan_automatizacion_reportes.md` |
| Instrucciones Hub Financiero | `/Users/jordi/Documents/Claude/Projects/Hub Financiero/CLAUDE.md` |

---

### Cómo trabajar con Jordi (recordatorio)

- Respuestas directas, sin postambles ni recaps. Si hay duda, preguntar UNA sola cosa.
- No confirmar de más — si ya está en CLAUDE.md o memoria.md, actuar directamente.
- Cuando Jordi aclara su intención, **escuchar primero** antes de implementar lo que parezca más inteligente.
- Deploy siempre en este orden: borrar webhook → push a GitHub → Manual Deploy en Render.
- Nunca copy-paste de código — arrastrar archivos a GitHub para evitar comillas tipográficas.
