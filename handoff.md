# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `docs/MEMORIA.md`.

---

## Sesión cerrada: 2026-05-27

### Objetivo
Corregir 3 bugs + sandbox multi-turno + confirmación de edición + paridad sandbox/producción + estructura .claude/ + reorganización docs/.

---

### Estado del código

| Item | Estado |
|------|--------|
| Versión | 26.6.0 |
| Branch | main |
| GitHub | ✅ sincronizado |
| Deploy en Render | ✅ AUTO — push a main dispara deploy |
| Ruta local | `/Users/jordi/Documents/Claude/Projects/Bot-gastos/` |

---

### Qué cambió en esta sesión (v26.1.0 → v26.6.0)

**Bug 1 — Edición no actualizaba presupuesto al cambiar subcategoría**
- `aplicar_edicion_contextual` y `_editar_gasto_local`: auto-deriva presupuesto desde `SUBCAT_PRESUPUESTO` si no viene explícito.

**Bug 2 — MEM_ aparecían en /corregir**
- `cargar_historial_compartido()`: filtro `UsuarioID > 0`.

**Bug 3 — ID incorrecto para presupuesto "Personal"**
- `PR["Personal"]` corregido a `829161723b0b49bf8787663a89c7248d`.
- Eliminada clave `"Cuidado personal"` de PR; SUBCAT_PRESUPUESTO y reglas hard-coded actualizadas.

**Feature — Sandbox multi-turno en /prueba**
- Loop persistente: registra y edita gastos sin guardar en Notion.
- Helpers: `_FOOTER_SB`, `_msg_sandbox()`, `_editar_gasto_local()`.
- Salida: `/cancelar`.

**Feature — Confirmación antes de aplicar edición contextual (producción)**
- Edición conversacional muestra propuesta con `[✅ Confirmar] [❌ Cancelar]` antes de tocar Notion.
- Múltiples correcciones se acumulan en `_staged_edits[uid]` (merging de campos).
- Solo al confirmar: PATCH a Notion + notificación a la pareja (un solo mensaje).
- `callback_edicion` maneja `pattern="^edicion_"`.

**Feature — Paridad sandbox/producción: confirmación en /prueba**
- Las ediciones en sandbox también muestran propuesta con `[✅ Confirmar] [❌ Cancelar]`.
- Al confirmar: solo actualiza `context.user_data["prueba_gasto"]`, sin Notion ni notificaciones.
- `callback_sandbox_edicion` maneja `pattern="^sandbox_"`.

**Infraestructura — Estructura .claude/**
- `.claude/settings.json`: modelo fijado a claude-sonnet-4-6, permisos Bash pre-aprobados.
- `.claude/hooks/SessionStart.sh`: carga automática de contexto al iniciar sesión.
- `.claude/commands/deploy.md`: comando /deploy con receta de 5 pasos.
- `.gitignore`: añadido `.claude/settings.local.json`.

**Reorganización — docs/**
- Movidos 7 archivos sueltos a carpeta `docs/`:
  MEMORIA.md, NOTION_SCHEMA.md, REGLAS_NEGOCIO.md, DEBUGGING.md, TESTING.md, REFLEXION_IA.md, GROQ_INTEGRATION.md
- `CLAUDE.md` actualizado con rutas `docs/` en sección de protocolo.

---

### Componentes clave (resumen)

| Componente | Tipo | Propósito |
|-----------|------|-----------|
| `_staged_edits` | dict global | Staging de ediciones pendientes de confirmar (producción) |
| `_construir_props_edicion(base, g)` | helper | Construye props Notion del diff base→g |
| `callback_edicion` | handler | Confirm/cancel edición real — pattern `^edicion_` |
| `callback_sandbox_edicion` | handler | Confirm/cancel edición en sandbox — pattern `^sandbox_` |
| `_FOOTER_SB` | constante | Footer de sandbox |
| `_msg_sandbox(gasto, header, origen)` | helper | Formatea gasto simulado con footer |
| `_editar_gasto_local(gasto, campos)` | helper | Aplica campos sin tocar Notion (shared por sandbox y staging) |

---

### Pendiente de verificación (después del deploy)

- [ ] Bug 1: "ponlo en Treat" → cambia subcategoría Y presupuesto
- [ ] Bug 2: /corregir → sin MEM_*
- [ ] Bug 3: "Corte de pelo 150" → presupuesto correcto en Notion
- [ ] Producción: editar gasto → ver propuesta → confirmar → solo entonces llega notificación a pareja
- [ ] Producción: 2 rondas de corrección → confirmar → un solo mensaje a pareja
- [ ] Sandbox: /prueba → gasto → corrección → ver propuesta → confirmar → corrección 2 → confirmar → /cancelar
- [ ] Sandbox: verificar que nada llega a Notion ni a la pareja en ningún momento

---

### Próximos pasos

1. Verificar los 7 puntos de arriba en producción y sandbox
2. **Backlog** (sin urgencia):
   - Reconciliación email BBVA — postergado indefinidamente
   - Evaluar búsqueda híbrida ciclo+calendario para casos genuinamente ambiguos
