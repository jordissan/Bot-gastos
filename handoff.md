# handoff.md — Estado operativo

> Se sobreescribe al final de cada sesión. Responde: ¿dónde quedó el proyecto?
> Para arquitectura técnica: `CLAUDE.md`. Para decisiones y lecciones: `memoria.md`.

---

## Sesión cerrada: 2026-05-26

### Objetivo
Corregir 3 bugs reportados + implementar sandbox multi-turno en /prueba.

---

### Estado del código

| Item | Estado |
|------|--------|
| Último commit | pendiente — ver abajo |
| GitHub | pendiente push |
| Ruta local | `/Users/jordi/Documents/Claude/Projects/Bot-gastos/` |
| Deploy en Render | ✅ AUTO — push a main dispara deploy |

---

### Qué cambió en esta sesión (v26.1.0 → v26.4.0)

**Bug 1 — Edición contextual no actualizaba presupuesto al cambiar subcategoría**
- `aplicar_edicion_contextual`: cuando se cambia subcategoría sin presupuesto explícito, ahora auto-deriva desde `SUBCAT_PRESUPUESTO`.

**Bug 2 — Filas MEM_ aparecían en /corregir**
- `cargar_historial_compartido()`: agregado filtro `UsuarioID > 0` para excluir filas de memoria.

**Bug 3 — ID incorrecto para presupuesto "Personal"**
- `PR["Personal"]` corregido a `829161723b0b49bf8787663a89c7248d` (BD Presupuesto).
- Eliminada clave `"Cuidado personal"` de PR (Jordi renombró la página).
- `SUBCAT_PRESUPUESTO["Cuidado personal"]` → `"Personal"`.
- Regla hard-coded de sephora/perfumería actualizada.
- `PR_EMOJI`: eliminada entrada `"Cuidado personal"`.

**Feature — Sandbox multi-turno en /prueba**
- `/prueba` ya no es un solo mensaje — abre un sandbox persistente.
- Cada mensaje puede ser un nuevo gasto O una corrección conversacional del gasto anterior.
- Nada toca Notion en ningún momento.
- Helpers nuevos: `_FOOTER_SB`, `_msg_sandbox()`, `_editar_gasto_local()`.
- Salida: `/cancelar` (mismo exit universal de todos los modos).
- El `ConversationHandler` no cambió — `handle_prueba` ahora devuelve `PRUEBA_GASTO` siempre (loop) en vez de `END`.

---

### Pendiente de verificación (después del deploy)

- [ ] Bug 1: Registrar algo → "ponlo en Treat" → debe cambiar subcategoría Y presupuesto
- [ ] Bug 2: /corregir → lista sin MEM_*
- [ ] Bug 3: Registrar "Corte de pelo 150" → verificar en Notion que Presupuesto apunta a la página correcta
- [ ] Sandbox: /prueba → registrar gasto → editar conversacionalmente → /cancelar

---

### Próximos pasos

1. Verificar los 4 puntos de arriba en producción
2. **Backlog** (sin urgencia):
   - Reconciliación email BBVA — postergado indefinidamente
   - Evaluar búsqueda híbrida ciclo+calendario para casos genuinamente ambiguos
