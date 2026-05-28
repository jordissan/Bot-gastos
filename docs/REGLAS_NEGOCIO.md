# REGLAS_NEGOCIO.md — Reglas de dominio y categorización

> Referencia de las reglas de negocio que gobiernan cómo se registran y clasifican los gastos.
> Las instrucciones explícitas de Jordi tienen prioridad absoluta sobre cualquier inferencia.

---

## Reglas de ciclo de pago (campo "Mes")

El campo `Mes` en Notion = **mes en que se paga**, no mes en que se compró.

| Tarjeta | Corte | Compra día X → Mes |
|---------|-------|---------------------|
| BBVA05 | 5 | X ≥ 5 → mes+1; X < 5 → mes actual |
| BBVA12 | 12 | X ≥ 12 → mes+1; X < 12 → mes actual |
| HEYB25 | 25 | X ≥ 25 → mes+2; X < 25 → mes+1 |
| BMEX04 | 4 | X ≥ 4 → mes+1; X < 4 → mes actual |
| EFVO | — | Siempre mes actual |

**Edge case días 1–4:** compras del 1–4 de cada mes pertenecen al ciclo anterior en BBVA12 y BBVA05.
Ejemplo: compra el 3-jun con BBVA12 → Mes = **JUN26** (no JUL26).

**Asignación automática de tarjeta** (si el usuario no especifica):
- Días 5–11 del mes → BBVA05
- Días 12 en adelante (y días 1–4) → BBVA12
- BMEX04 y HEYB25: solo si Jordi las menciona explícitamente

**Mes activo** (para `/resumen` y consultas "este mes"):
- Hoy ≥ día 5 → mes siguiente
- Hoy < día 5 → mes actual

---

## Reglas de categorización

### Jerarquía de resolución (en orden)
1. Instrucción explícita de Jordi → prioridad absoluta
2. Reglas hard-coded (ver lista abajo)
3. Alias aprendidos (BD Alias Bot, por usuario)
4. Aprendizaje por similitud (BD Aprendizaje, >80% match)
5. Google Maps Places API (categoría del negocio)
6. Pregunta al usuario (menú grupo → subcategoría)

### Casos especiales con regla fija

| Comercio / concepto | Subcategoría | Presupuesto | Notas |
|---------------------|-------------|-------------|-------|
| Calii Calii | Super | Despensa | Registrar como "Super (Calii)". Nunca como Restaurantes. |
| Oxxo | Abarrotes | Despensa | |
| Oxxo Gas | Gasolina | Automovil | **Distinto a Oxxo**. Nunca confundir. |
| Farmacias (Guadalajara, Benavides, etc.) | Medicina | Salud | Nombre completo de la farmacia siempre |
| Cualquier gasto de Ezra | Ezra | Ezra | **SIEMPRE Presupuesto=Ezra**. Subcategoría=tipo real (pañales, comida, ropa…). NUNCA Ezra como subcategoría. |
| Renta | Renta | Renta | **NO es deuda**. Nunca poner en Deuda. |
| MSI (meses sin intereses) | MSI | MSI | Formato: "Concepto X/Total" ej. "MacBook Pro 4/18" |

### "Restaurantes" — caso de ambigüedad

"Restaurantes" existe en **SC (subcategoría)** Y en **PR (presupuesto)**. Son páginas distintas con IDs distintos.
- **Regla:** cuando el usuario dice "restaurantes", usar `subcategoria=Restaurantes` (más preciso).
- El presupuesto "Restaurantes" en PR se usa automáticamente vía `SUBCAT_PRESUPUESTO`.
- **NUNCA poner `subcategoria` y `categoria` simultáneamente en el plan de consulta.**

### Reglas de subcategoría vs categoría

- `subcategoria` = **qué** compraste (Abarrotes, Gasolina, Treat…)
- `categoria` (presupuesto) = **a qué bolsa va** (Despensa, Automovil, Diversión…)
- No siempre son iguales: un gasto de "Gasolina" (subcategoría) va a "Automovil" (presupuesto).
- En consultas NL, el planner debe elegir uno u otro, nunca ambos.

---

## Reglas de registro de gastos

### Monto
- Sin decimales salvo que Jordi los especifique
- Monto ≥ $5,000 → pedir confirmación con botones inline antes de guardar
- Nunca registrar monto 0 o negativo

### Fecha
- Sin fecha en el mensaje → fecha = hoy (America/Mexico_City)
- "ayer" → día anterior en MX
- Formatos aceptados: `15-may`, `15/05`, `15 mayo`, `ayer`, `hoy`
- Siempre verificar la fecha real del sistema — nunca asumir

### Concepto
- Usar el nombre real del comercio, no abreviaturas inventadas
- Farmacias: nombre completo (Farmacia Guadalajara, Farmacia Benavides)
- Tickets con desglose de productos: el concepto lleva `*` al final (ej. `Walmart*`)

### Multi-gasto
- Por coma en formato estricto: `super 350, gasolina 500`
- En lenguaje natural: "fui al súper 350 y cargué gasolina 500" → clasificador devuelve `multi_gasto`
- Confirmación agrupada: "✅ 2 gastos registrados"

---

## Reglas de ingresos estimados

- Solo Jordi o Nane pueden declarar ingreso (cualquiera de los dos)
- Se guarda en Metas Bot con `presupuesto="INGRESO"` y el ciclo específico
- Se puede actualizar en cualquier momento — el upsert sobreescribe
- Se busca en **ambos UIDs** al leer (finanzas conjuntas)
- Si no hay ingreso declarado para el ciclo activo, `posicion_financiera` lo indica

---

## Reglas de MSI

- Formato obligatorio: `"Nombre del bien X/Total"` donde X = pago actual, Total = total de pagos
- Ejemplos válidos: `"MacBook Pro 4/18"`, `"Mapfre 3/12"`, `"iPhone 17 Pro 2/18"`
- El número X se incrementa manualmente cada mes — el bot no lo incrementa automáticamente
- `msi_tracker` usa regex `^(.+?)\s+(\d{1,2})\s*/\s*(\d{1,2})\s*$` para parsear

---

## Reglas de edición

- Solo `aplicar_edicion_contextual` puede modificar gastos — es la **única ruta de escritura**
- La edición contextual ("cámbialo a 400") aplica sobre `last_gasto` en RAM (el último registrado)
- `/corregir` muestra los últimos 5 gastos combinados de ambos usuarios (cualquiera puede corregir el del otro)
- Los 6 campos editables: monto, fecha, tarjeta, categoría (subcategoría), presupuesto, concepto
- `/eliminar` hace soft-delete: pone `Archivado=True` en Notion, no borra la página

---

## Reglas de notificación

- Cada acción de uno se notifica al otro (`USUARIOS_NOTIFICAR`)
- Las alertas de hormiga, anomalía e insight se envían **solo al que registró** (no al otro)
- Los reportes van a **ambos usuarios**

---

## Gastos fijos conocidos (referencia)

### Servicios recurrentes (~$1,822/mes)
| Servicio | Monto | Tarjeta | Día aprox |
|----------|-------|---------|-----------|
| Spotify | $189 | BBVA05 | 6 |
| Adobe | $276.89 | BBVA05 | 7 |
| iCloud (Nane) | $165 | BBVA05 | 10 |
| CapCut | $66 | BBVA05 | 22 |
| Izzi | $590 | BBVA12 | 13 |
| Claude.ai | $346.97 | BBVA12 | 16 |
| Google | $39 | BMEX04 | 6 |
| Disney+ | $149 | HEYB25 | 30 |

### MSI activos (~$4,172/mes)
| Concepto | Monto/mes | Tarjeta | Día |
|----------|-----------|---------|-----|
| iPhone 17 Pro | $1,049.75 | BBVA12 | 12 |
| MacBook Pro | $1,355.42 | BMEX04 | 4 |
| Mapfre X/12 | $986 | BBVA12 | 12 |
| Efectivo EFI X/24 | $780.68 | BBVA12 | 12 |

### Efectivo fijo (~$12,770/mes)
| Concepto | Monto | Tarjeta | Día |
|----------|-------|---------|-----|
| Renta | $9,300 | EFVO | 15 |
| Digitt | $2,212.60 | EFVO | 15 (1/15 completado abr 2026) |
| BBVA PR | $495 | EFVO | 15 y 30 |
| PD HEYB25 | $767.81 | HEYB25 | 6 (24 pagos hasta abr 2028) |

**Total comprometido estimado: ~$18,764/mes** antes de gasto variable.
