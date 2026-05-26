# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `memoria.md`.
>
> **Al cerrar la sesión:** actualizar este archivo + los demás `.md` que correspondan según
> lo que se hizo. Ver tabla en `CLAUDE.md → Protocolo de Cierre`. Luego commit + push.
> Jordi no debería tener que pedir esto.

---

## Sesión cerrada: 2026-05-20 → 2026-05-26

### Objetivo
Expandir el bot a un hub financiero completo (Hub v2), corregir bugs de subcategoría y alucinación de Groq, y construir la estructura completa de documentación del proyecto.

---

### Estado del código

| Item | Estado |
|------|--------|
| Último commit | `a76faf0` — "actualiza ruta local del proyecto" |
| GitHub | ✅ Pusheado — branch `main` |
| Ruta local | `/Users/jordi/Documents/Claude/Projects/Bot-gastos/` |
| Deploy en Render | ✅ **AUTO** — Render despliega automáticamente en cada push a `main` |
| Bot en producción | ✅ Corriendo con el código de esta sesión |

---

### Qué cambió en esta sesión

**bot.py:**
- Filtro por `subcategoria_id` en `ejecutar_consulta_finanzas` y todos los modos de `_datos_consulta_especial`
- Filtro por `tarjeta` (campo `rich_text`) en todas las queries
- Plan carryover: `last_query` inyectado al planner para mantener filtros entre preguntas
- Ingresos estimados: nuevo intent `ingreso` + handler completo
- 4 nuevos modos: `msi_tracker`, `oportunidades_ahorro`, `posicion_financiera`, `tendencia_ingresos`
- Desglose por tarjeta en reportes (`por_tarjeta` en `_agg_ciclo`)
- `gastos_raw` limit: 10 → 20
- Helper `_ciclo_a_rango_calendario(ciclo)` (sin uso activo aún)
- `prompt_resp` con REGLA CRÍTICA anti-alucinación
- APScheduler: `job_reporte_semanal` (lun 9am MX) y `job_reporte_mensual` (día 5 2pm MX)

**Qué se intentó y revirtió:**
- Auto-retry por mes calendario — revertido. Ver `memoria.md`.

**Documentación creada (estructura completa):**
- `CLAUDE.md` — arquitectura técnica (restructurado)
- `memoria.md` — memoria institucional
- `handoff.md` — estado operativo por sesión (este archivo)
- `NOTION_SCHEMA.md` — schema de las 6 BDs con todos los IDs y tipos
- `REGLAS_NEGOCIO.md` — reglas de dominio, categorización, gastos fijos
- `DEBUGGING.md` — guía de diagnóstico síntoma→solución
- `TESTING.md` — checklist de verificación post-deploy

**Infraestructura:**
- Carpeta movida de `/Users/jordi/Bot-gastos/` a `/Users/jordi/Documents/Claude/Projects/Bot-gastos/`

---

### Pendiente de verificación (después del deploy)

- [ ] Anti-alucinación: preguntar por un ciclo sin gastos → debe decir "no hay" sin mencionar otros meses
- [ ] `msi_tracker`: confirmar parseo del formato "Concepto X/Total" con datos reales
- [ ] `posicion_financiera`: declarar ingreso y consultar "¿cómo voy este mes?"
- [ ] Logs de Render: `[APScheduler] Scheduler iniciado. Jobs: reporte_semanal (lun 9am), reporte_mensual (día 5 2pm)`

---

### Próximos pasos

1. **Verificar los 4 puntos de arriba en producción** con `TESTING.md` como guía
   — el deploy ya ocurrió automáticamente con el último push

3. **Backlog** (sin urgencia):
   - Reconciliación email BBVA — postergado indefinidamente (ver `memoria.md`)
   - Evaluar búsqueda híbrida ciclo+calendario para casos genuinamente ambiguos
