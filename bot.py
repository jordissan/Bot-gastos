import os
import json
import datetime
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
 
# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_TOKEN      = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
 
# ─── PROMPT PARA CLAUDE ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """
Eres un asistente que extrae datos de gastos personales y los convierte en JSON.
 
REGLAS DE TARJETA (si no se menciona, inferir por fecha):
- Días 1-11 del mes → BBVA05
- Días 12-31 del mes → BBVA12
 
REGLAS DE MES (mes al que se carga el gasto):
- BBVA12 (corte día 12): compra entre día 12 de un mes y día 11 del siguiente → Mes = mes+2
  Ejemplo: compra 15-mar → MAY26
- BBVA05 (corte día 5): compra entre día 5 de un mes y día 4 del siguiente → Mes = mes+1
  Ejemplo: compra 20-mar → ABR26
 
SUBCATEGORÍAS por concepto (inferir si no se dice):
- Netflix, Spotify, Disney, HBO, Apple → Streaming
- Starbucks, cafe, bar, restaurante, comida, taco, pizza → Diversión
- Farmacia, doctor, medicamento, salud → Salud
- Gasolina, uber, didi, transporte → Transporte
- Supermercado, Soriana, Walmart, Costco, abarrotes → Despensa
- Amazon, tienda, ropa, zapatos → Compras
- CFE, agua, gas, internet, Izzi, Telmex → Servicios
- Cualquier otro → General
 
PRESUPUESTO (basado en subcategoría):
- Streaming → Servicios
- Diversión → Diversión
- Salud → Salud
- Transporte → Transporte
- Despensa → Despensa
- Compras → Compras
- Servicios → Servicios
- General → General
 
Hoy es: {today}
 
Responde ÚNICAMENTE con un objeto JSON válido sin ningún texto adicional, sin markdown, sin explicaciones, sin bloques de código. Solo el JSON puro:
{{"concepto": "nombre del gasto", "monto": 000.00, "fecha": "YYYY-MM-DD", "tarjeta": "BBVA12 o BBVA05", "mes": "MMM26", "subcategoria": "la subcategoría", "presupuesto": "el presupuesto"}}
"""
 
# ─── FUNCIÓN: CLAUDE INTERPRETA EL GASTO ─────────────────────────────────────
def interpretar_gasto(texto: str) -> dict:
    today = datetime.date.today().strftime("%d-%b-%Y")
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-opus-4-5",
            "max_tokens": 500,
            "system": SYSTEM_PROMPT.format(today=today),
            "messages": [{"role": "user", "content": texto}],
        },
    )
    data = response.json()
    
    # Extraer el texto de la respuesta
    raw = ""
    if "content" in data and len(data["content"]) > 0:
        raw = data["content"][0].get("text", "").strip()
    else:
        raise ValueError(f"Respuesta inesperada de Claude: {data}")
    
    # Limpiar posibles bloques de código markdown
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    return json.loads(raw)
 
# ─── FUNCIÓN: CREAR ENTRADA EN NOTION ────────────────────────────────────────
def guardar_en_notion(gasto: dict) -> bool:
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Concepto": {
                "title": [{"text": {"content": gasto["concepto"]}}]
            },
            "Monto": {
                "number": gasto["monto"]
            },
            "Fecha": {
                "date": {"start": gasto["fecha"]}
            },
            "Estado de Cuenta": {
                "select": {"name": gasto["tarjeta"]}
            },
            "Mes": {
                "select": {"name": gasto["mes"]}
            },
            "Subcategoría": {
                "select": {"name": gasto["subcategoria"]}
            },
            "Presupuesto": {
                "select": {"name": gasto["presupuesto"]}
            },
        },
    }
    r = requests.post(url, headers=headers, json=payload)
    return r.status_code == 200
 
# ─── HANDLER PRINCIPAL ───────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    await update.message.reply_text("⏳ Procesando...")
 
    try:
        gasto = interpretar_gasto(texto)
        guardado = guardar_en_notion(gasto)
 
        if guardado:
            msg = (
                f"✅ *Gasto guardado*\n\n"
                f"📌 *{gasto['concepto']}*\n"
                f"💰 ${gasto['monto']:,.2f}\n"
                f"📅 {gasto['fecha']}\n"
                f"💳 {gasto['tarjeta']}\n"
                f"🗓️ Mes: {gasto['mes']}\n"
                f"🏷️ {gasto['subcategoria']} → {gasto['presupuesto']}"
            )
        else:
            msg = "⚠️ Se interpretó el gasto pero hubo un error al guardarlo en Notion."
 
        await update.message.reply_text(msg, parse_mode="Markdown")
 
    except Exception as e:
        await update.message.reply_text(
            f"❌ No pude procesar ese mensaje.\n\nError: {str(e)}\n\nIntenta así:\n`Starbucks 150` o `Gasolina 500 BBVA05`",
            parse_mode="Markdown"
        )
 
# ─── ARRANQUE ────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot corriendo...")
    app.run_polling()
 
if __name__ == "__main__":
    main()
