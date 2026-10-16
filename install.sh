#!/bin/sh
# Install a GNOME launcher + icon for the current checkout (user-level).
set -e
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
cp "$D/data/org.fnirsi.DMM.svg" ~/.local/share/icons/hicolor/scalable/apps/
cat > ~/.local/share/applications/org.fnirsi.DMM.desktop <<EOT
[Desktop Entry]
Type=Application
Name=FNIRSI 2D15P Multimeter
Comment=Live multimeter readings from the FNIRSI 2D15P
Exec=env "PYTHONPATH=$D" python3 -m fnirsi_dmm_gui
Icon=org.fnirsi.DMM
Categories=Utility;Electronics;
StartupWMClass=org.fnirsi.DMM
Terminal=false
EOT
update-desktop-database ~/.local/share/applications 2>/dev/null || true
gtk-update-icon-cache -q ~/.local/share/icons/hicolor 2>/dev/null || true
echo "Installed. Launch 'FNIRSI 2D15P Multimeter' from the GNOME app grid."
