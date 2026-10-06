#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${DOCUMENT_KIT_HOME:-$HOME/.local/share/document-kit}"
BIN_DIR="${DOCUMENT_KIT_BIN_DIR:-$HOME/.local/bin}"

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
echo "Next:"
echo "  document-kit init --workspace ~/Desktop/Repitte"
echo "  document-kit doctor"
