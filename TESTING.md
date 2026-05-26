# TESTING.md — Verificación manual post-deploy

> Ejecutar en orden después de cada deploy. Cada test tiene un input exacto y el output esperado.
> Si alguno falla, ver `DEBUGGING.md` antes de investigar el código.

---

## 0. Verificación de arranque (antes de cualquier test)

En logs de Render confirmar:
- `[APScheduler] Scheduler iniciado. Jobs: reporte_semanal (lun 9am), reporte_mensual (día 5 2pm)`
- Sin tracebacks ni errores de importación

---

## 1. Registro de gastos

### 1a. Texto libre básico
**Input:** `"gasté 150 en starbucks"`
**Esperado:** confirmación con concepto, monto $150, tarjeta BBVA12 o BBVA05 (según día), ciclo correcto, categoría Treat/Diversión.

### 1b. Formato estricto
**Input:** `"Starbucks 150 BBVA05 ayer"`
**Esperado:** misma confirmación, tarjeta BBVA05, fecha = ayer. Debe procesarse SIN llamar a Groq (más rápido).

### 1c. Monto alto (confirmación)
**Input:** `"gasté 6000 en muebles"`
**Esperado:** bot pide confirmación con botones ✅ Confirmar / ❌ Cancelar antes de guardar.

### 1d. Multi-gasto
**Input:** `"súper 350, gasolina 500"`
**Esperado:** "✅ 2 gastos registrados" con ambos conceptos.

### 1e. Gasto con fecha explícita
**Input:** `"farmacia guadalajara 200 el 15 de mayo"`
**Esperado:** Fecha = 15/MAY/26, nombre completo de la farmacia, Subcategoría = Medicina.

### 1f. Gasto de Ezra
**Input:** `"pañales 350"`
**Esperado:** Presupuesto = Ezra, Subcategoría = algo relevante (no Ezra). Si el bot no sabe, pregunta.

---

## 2. Ciclos de pago — verificación de asignación

### 2a. Compra con BBVA12 en día ≥ 12
**Input:** `"Netflix 250 BBVA12"` (hacer en día ≥ 12 del mes)
**Esperado:** Mes = mes siguiente. Ej. si hoy es 26-may → Mes = JUN26.

### 2b. Compra con EFVO
**Input:** `"renta 9300 efvo"`
**Esperado:** Mes = mes actual siempre. Si hoy es 26-may → Mes = MAY26.

### 2c. Compra con HEYB25 en día ≥ 25
**Input:** `"Disney+ 149 heyb25"` (hacer en día ≥ 25)
**Esperado:** Mes = mes+2. Si hoy es 26-may → Mes = JUL26.

---

## 3. Consultas en lenguaje natural (Hub Financiero)

### 3a. Total del mes activo
**Input:** `"¿cuánto he gastado este mes?"`
**Esperado:** total en pesos, lista de categorías con montos, período correcto.

### 3b. Filtro por subcategoría
**Input:** `"¿cuánto he gastado en abarrotes este mes?"`
**Esperado:** total SOLO de gastos con Subcategoría=Abarrotes, no el total de Despensa.

### 3c. Filtro por tarjeta
**Input:** `"¿cuánto he gastado con BBVA12 este mes?"`
**Esperado:** total solo de gastos donde Tarjeta=BBVA12.

### 3d. Filtro por ciclo específico
**Input:** `"dame los gastos de abarrotes de MAY26"` (ciclo ya cerrado)
**Esperado:** lista real de gastos de Abarrotes en Mes=MAY26. Si no hay, decirlo sin inventar.

### 3e. Anti-alucinación (crítico)
**Input:** preguntar por un ciclo sin gastos, ej. `"gastos de FEB25"` si no hay datos ahí.
**Esperado:** "No encontré gastos para FEB25" o similar. **NUNCA** debe mencionar datos de otros meses ni inventar cifras.

### 3f. Consulta histórica
**Input:** `"¿cuánto llevo pagado en total de gasolina?"`
**Esperado:** aviso "🔍 Buscando en toda la historia…" y luego total histórico.

### 3g. Plan carryover
**Input (2 mensajes seguidos):**
1. `"¿cuánto gasté en abarrotes este mes?"`
2. `"¿y el mes pasado?"`
**Esperado:** el segundo mensaje debe recordar el filtro `subcategoria=Abarrotes` sin que se lo repitas.

### 3h. MSI tracker
**Input:** `"¿qué MSIs tengo activos?"`
**Esperado:** lista de MSIs con pagos restantes y compromiso mensual total.

### 3i. Posición financiera
**Setup:** primero declarar `"este mes esperamos ganar $50,000"`
**Input:** `"¿cómo voy este mes?"`
**Esperado:** % gastado, saldo libre, proyección.

---

## 4. Edición y corrección

### 4a. Edición contextual inmediata
**Input (2 mensajes seguidos):**
1. `"Starbucks 150"` (registra el gasto)
2. `"cámbialo a 180"`
**Esperado:** el gasto anterior se actualiza a $180 en Notion.

### 4b. `/corregir`
**Input:** `/corregir`
**Esperado:** lista de los últimos 5 gastos (de ambos usuarios). Al elegir un número, aparece el panel inline con los 6 campos editables.

### 4c. `/eliminar`
**Input:** `/eliminar`
**Esperado:** pide confirmación. Al confirmar, el último gasto queda `Archivado=True` en Notion (NO se borra).

---

## 5. Comandos

### 5a. `/resumen`
**Input:** `/resumen`
**Esperado:** tabla por categoría del mes activo + proyección de cierre + narrativa de Groq.

### 5b. `/top`
**Input:** `/top`
**Esperado:** top 5 gastos más caros del mes.

### 5c. `/buscar`
**Input:** `/buscar starbucks`
**Esperado:** lista de gastos con "starbucks" en el concepto, últimos 12, con suma total.

### 5d. `/reporte`
**Input:** `/reporte`
**Esperado:** reporte semanal enviado a ambos usuarios (Jordi y Nane).

---

## 6. Memoria persistente

### 6a. Referencia contextual
**Input (2 mensajes seguidos):**
1. `"¿cuánto gasté en gasolina este mes?"` (el bot devuelve una lista)
2. `"dame el link del más caro"`
**Esperado:** el bot devuelve el deep link de Notion del gasto de gasolina más caro de la lista anterior.

### 6b. Sobrevive reinicio
1. Registrar un gasto
2. Esperar que Render haga un reinicio natural (o forzarlo con Manual Deploy)
3. Preguntar `"dame el link del último gasto"`
**Esperado:** el bot recuerda el gasto incluso después del reinicio (lo carga de Historial Bot).

---

## 7. Alertas inteligentes

### 7a. Gasto hormiga
**Setup:** registrar 3+ gastos < $150 en Treat o Abarrotes en los últimos 7 días.
**Esperado:** al registrar el cuarto, aparece alerta "☕ Llevas N gastos en X esta semana ($total)".

### 7b. Anomalía de monto
**Setup:** haber registrado el mismo concepto varias veces con montos similares.
**Input:** registrar el mismo concepto con monto 3x mayor al usual.
**Esperado:** alerta "⚠️ X por $Y parece inusual…" después de la confirmación normal.

---

## Criterios de aprobación

| Test | Crítico | Notas |
|------|---------|-------|
| 1a, 1b | ✅ Crítico | Base del bot |
| 1c | ✅ Crítico | Evita guardar montos erróneos |
| 3b | ✅ Crítico | Bug más frecuente (subcategoría vs categoría) |
| 3e | ✅ Crítico | Anti-alucinación |
| 3g | ✅ Crítico | Plan carryover |
| 4a, 4b | ✅ Crítico | Edición |
| 6a | ✅ Crítico | Memoria |
| Resto | ⚪ Importante | Verificar cuando sea posible |
