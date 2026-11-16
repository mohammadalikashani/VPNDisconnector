#!/bin/bash
# Installs the VPN-bypass helper as a LaunchAgent so it starts at login.
# Uninstall:  ./install.sh uninstall
set -euo pipefail

LABEL="com.vpndisconnector.helper"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SCRIPT="$(cd "$(dirname "$0")" && pwd)/bypass_proxy.py"
PY="$(command -v python3)"
PORT="${PORT:-8899}"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [[ "${1:-}" == "uninstall" ]]; then
  rm -f "$PLIST"
  echo "Helper uninstalled."
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$SCRIPT</string><string>--port</string><string>$PORT</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/vpn-disconnector.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/vpn-disconnector.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 1
curl -s "http://127.0.0.1:$PORT/health" && echo && echo "Helper installed and running on port $PORT."
