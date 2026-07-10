#!/usr/bin/env bash
# Установка mindmap: скрипты в ~/bin + скилл в найденных агентов.
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$HOME/bin"
cp "$REPO"/mindmap-canvas.py "$REPO"/mindmap-canvas-tk.py \
   "$REPO"/mindmap-review.py "$REPO"/mindmap-ascii.py "$HOME/bin/"
chmod +x "$HOME"/bin/mindmap-*.py
echo "✓ скрипты в ~/bin"

if [ -d "$HOME/.claude" ]; then
  mkdir -p "$HOME/.claude/skills/mindmap"
  cp "$REPO/integrations/claude-code/SKILL.md" "$HOME/.claude/skills/mindmap/"
  echo "✓ Claude Code: скилл mindmap"
fi

if [ -d "$HOME/.pi/agent/extensions" ]; then
  cp "$REPO/integrations/pi/mindmap.ts" "$HOME/.pi/agent/extensions/"
  echo "✓ Pi: расширение mindmap.ts"
fi

if [ -d "$HOME/.openclaude" ]; then
  mkdir -p "$HOME/.openclaude/skills/mindmap"
  cp "$REPO/integrations/openclaude/SKILL.md" "$HOME/.openclaude/skills/mindmap/"
  echo "✓ OpenClaude: скилл mindmap (hook_prompt.txt подключи в конфиге сам)"
fi

command -v google-chrome >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 || \
  command -v chromium-browser >/dev/null 2>&1 || \
  echo "! Chrome/Chromium не найден - канвас откроется через Tk-fallback (mindmap-canvas-tk.py)"

echo "Готово. Скажи своему агенту «объясни X» или позови /mindmap."
