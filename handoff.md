# handoff.md — Estado operativo del proyecto

> Este archivo se sobreescribe al final de cada sesión de trabajo.
> Describe el estado exacto en el que quedó el proyecto — qué se hizo, qué falló, qué sigue.
> Para contexto histórico y decisiones de diseño, ver `memoria.md`.

---

## Sesión cerrada: 2026-05-20 → 2026-05-26

### Objetivo de la sesión
Expandir el bot de gastos a un hub financiero completo con consultas avanzadas, y corregir bugs
de subcategoría, alucinación de Groq y (más tarde) confusión de ciclo de pago.

---

### Estado actual del proyecto

| Aspecto | Estado |
|---------|--------|
| Código en GitHub | ✅ Pusheado — branch `main`, commit `f89b40a` |
| Deploy en Render | ⚠️ **PENDIENTE** — Manual Deploy no realizado |
| Tests manuales | Parciales — el fix de alucinación no se pudo verificar en Render |
| Bot funcionando | Sí, con el código anterior (pre-sesión) hasta que se haga el deploy |

---

### Archivos modificados en esta sesión

| Archivo | Qué cambió |
|---------|------------|
| `bot.py` | Ver detalle abajo — cambios mayores |
| `CLAUDE.md` | Actualizado a v26.2.0 + instrucción de leer `memoria.md` al inicio |
| `memoria.md` | Creado en esta sesión |
| `handoff.md` | Creado en esta sesión (este archivo) |
| `requirements.txt` | APScheduler==3.10.4 y pytz>=2024.1 agregados (sesión previa) |

---

### Cambios en bot.py — detalle

#### Agregado permanentemente ✅

1. **`ejecutar_consulta_finanzas` — filtro `subcategoria_id`**
   - Deriva `subcategoria_id` del dict `SC` usando el campo `plan["subcategoria"]`
   - Filtra en los tres loops (por fecha, por mes, histórico) comparando contra la relación `Subcategoria` de Notion

2. **`_datos_consulta_especial` — propagación de subcategoría a todos los modos**
   - Extrae `subcategoria_id` al inicio de la función
   - Lo pasa a TODOS los `_gastos_recientes()` y `ejecutar_consulta_finanzas()` internos

3. **Filtro por tarjeta en consultas**
   - `tarjeta_filtro` (plan["tarjeta"]) se aplica en los tres loops de `ejecutar_consulta_finanzas`
   - Lee campo `rich_text` de Notion (no select) — `props.get("Tarjeta", {}).get("rich_text", [])`
   - El planner genera `"tarjeta": null` por defecto, solo lo llena si el usuario lo menciona explícitamente

4. **Plan carryover en el planner**
   - `last_query` de la memoria RAM se inyecta en el prompt del planner
   - Permite resolver "¿y la semana pasada?" / "¿y con BBVA12?" sin perder contexto

5. **Ingresos estimados freelance**
   - Clasificador detecta frases de ingreso (`esperamos ganar`, `vamos a ganar`, `ingreso del mes`)
   - Guarda en Metas Bot con `presupuesto="INGRESO"` vía `guardar_meta(uid, "INGRESO", monto, ciclo)`
   - Muestra posición financiera inmediata al declarar ingreso

6. **Nuevos modos en `_datos_consulta_especial`:**
   - `msi_tracker` — MSIs activos con pagos restantes y compromiso mensual
   - `oportunidades_ahorro` — últimos 3 meses vs promedio histórico de 6 meses por categoría
   - `posicion_financiera` — ingreso estimado vs gasto real, % gastado, saldo libre
   - `tendencia_ingresos` — últimos 6 ciclos ingreso declarado vs gasto real

7. **Desglose por tarjeta en reportes**
   - `_agg_ciclo` ahora devuelve `por_tarjeta` (dict tarjeta → monto)
   - Reportes semanal y mensual incluyen ese desglose en Telegram y correo

8. **`gastos_raw` limit:** 10 → 20

9. **`_ciclo_a_rango_calendario(ciclo)`** — helper que convierte "JUN26" → (date(2026,6,1), date(2026,6,30))
   - Se mantiene en el código aunque el auto-retry fue eliminado — puede ser útil en el futuro

10. **Anti-alucinación en `prompt_resp`**
    - Cambio de "Responde usando SOLO estos datos" por REGLA CRÍTICA explícita
    - Prohíbe explícitamente usar datos de mensajes anteriores o inventar meses

11. **APScheduler (sesión previa)**
    - `job_reporte_semanal`: lunes 9am MX (cron `0 15 * * 1` UTC)
    - `job_reporte_mensual`: día 5 2pm MX (cron `0 20 5 * *` UTC)
    - Se inicializan en `main()` antes de `app.run_webhook()`

#### Intentado y revertido ❌

- **Auto-retry por mes calendario** — cuando `Mes=JUN26` devolvía vacío, se reintentaba
  con `fecha_desde/fecha_hasta` del mes calendario.
  - **Por qué se revirtió:** el usuario aclaró que `JUN26` = ciclo de pago en Notion,
    no mes calendario. El bot debe respetar esa semántica. Si no hay gastos en JUN26, decirlo.
  - El helper `_ciclo_a_rango_calendario` se dejó en el código por si se necesita en el futuro.

---

### Qué se intentó que no funcionó

1. **Rutinas remotas de Claude Code para reportes** — las rutinas CCR no pueden hacer
   llamadas HTTP salientes desde Render. Se reemplazaron con APScheduler dentro del bot.

2. **Auto-retry calendario** — ver arriba.

---

### Próximos pasos (en orden de prioridad)

#### Inmediato — antes de la próxima sesión
- [ ] **Deploy en Render** (Jordi, manual): Render → Bot-gastos → Manual Deploy → Restart
  - Verificar en logs: `[APScheduler] Scheduler iniciado. Jobs: reporte_semanal (lun 9am), reporte_mensual (día 5 2pm)`
  - Verificar que el fix de alucinación funciona: preguntar por un ciclo sin gastos y confirmar que el bot dice "no hay" sin inventar

#### Próxima sesión — bugs y mejoras pendientes
- [ ] Verificar que el fix de anti-alucinación funciona en producción después del deploy
- [ ] Probar `msi_tracker` con datos reales — confirmar que parsea bien "Concepto X/Total"
- [ ] Probar `posicion_financiera` declarando un ingreso y consultando

#### Backlog
- [ ] Email BBVA reconciliación (Gmail API + parsear PDF de estado de cuenta y cruzar con Notion)
  — alta complejidad, postergado indefinidamente
- [ ] Evaluar si tiene sentido agregar un modo de búsqueda híbrido (ciclo + fecha calendario)
  cuando el contexto de la pregunta es ambiguo — pero NO por defecto

---

### Contexto de trabajo rápido (para retomar sin leer todo)

```
Repo:    github.com/jordissan/Bot-gastos (main)
URL bot: https://bot-gastos-socj.onrender.com
Stack:   Python 3.11 · python-telegram-bot 21.3 · Groq · Notion · APScheduler · Docker en Render
Deploy:  borrar webhook → push GitHub → Manual Deploy en Render
Jordi:   8663298433 | Nane: 8093171397 | Finanzas conjuntas (no separar por usuario)
```
