#!/bin/bash
# Carga automática de contexto al iniciar sesión en Bot-gastos.
# Claude lee este output como contexto inicial — sin necesidad de pedir handoff manualmente.

PROJECT="/Users/jordi/Documents/Claude/Projects/Bot-gastos"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  BOT-GASTOS — CONTEXTO AUTOMÁTICO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Versión actual del bot
VERSION=$(grep -o 'Bot corriendo [0-9.]*' "$PROJECT/bot.py" 2>/dev/null | head -1 | awk '{print $3}')
echo "📦 Versión: ${VERSION:-desconocida}"

# Estado git
BRANCH=$(git -C "$PROJECT" branch --show-current 2>/dev/null)
UNCOMMITTED=$(git -C "$PROJECT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
LAST_COMMIT=$(git -C "$PROJECT" log -1 --format="%h — %s" 2>/dev/null)
echo "🔀 Branch: ${BRANCH} | Sin commitear: ${UNCOMMITTED}"
echo "📝 Último commit: ${LAST_COMMIT}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  HANDOFF — ESTADO DE LA ÚLTIMA SESIÓN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$PROJECT/handoff.md"
