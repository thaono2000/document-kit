#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${DOCUMENT_KIT_HOME:-$HOME/.local/share/document-kit}"
BIN_DIR="${DOCUMENT_KIT_BIN_DIR:-$HOME/.local/bin}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required." >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"ERROR: DocumentKit requires Python 3.11+, found {sys.version.split()[0]}")
print(f"Python OK: {sys.version.split()[0]}")
PY

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required." >&2
  exit 1
fi
echo "Git OK: $(git --version)"

for tool in codebase-memory-mcp agent; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "$tool OK: $(command -v "$tool")"
  else
    echo "WARNING: $tool is not currently on PATH. Installation can continue, but the default high-trust workflow will fail doctor/build until this tool is available or document-kit.toml is configured differently." >&2
  fi
done

mkdir -p "$DEST" "$BIN_DIR"
rm -rf "$DEST/documentkit"
cp -R "$ROOT/documentkit" "$DEST/documentkit"

cat > "$BIN_DIR/document-kit" <<LAUNCHER
#!/usr/bin/env bash
export PYTHONPATH="$DEST\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m documentkit "\$@"
LAUNCHER
chmod 755 "$BIN_DIR/document-kit"

echo "Installed DocumentKit: $BIN_DIR/document-kit"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "NOTE: $BIN_DIR is not in PATH. Add: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo
echo "Recommended layout:"
echo "  ~/Tools/document-kit/      # this tool repository"
echo "  ~/Desktop/Repitte/         # analyzed workspace"
echo
echo "Next:"
echo "  cd ~/Desktop/Repitte"
echo "  document-kit init --workspace ."
echo "  document-kit doctor"
