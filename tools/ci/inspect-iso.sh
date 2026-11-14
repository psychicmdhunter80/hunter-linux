#!/usr/bin/env bash
# Print the parts of a built Hunter Linux image that decide how it boots.
#
#   inspect-iso.sh <iso> <work-directory>
#
# The ISO is unpacked without root: xorriso pulls out live/filesystem.squashfs
# and unsquashfs expands it.  Only configuration, package names and file modes
# are printed - never password hashes.
set -uo pipefail

ISO="${1:?usage: inspect-iso.sh <iso> <workdir>}"
WORK="${2:?work directory required}"
ROOT="$WORK/rootfs"

mkdir -p "$WORK"
xorriso -osirrox on -indev "$ISO" -extract /live/filesystem.squashfs \
	"$WORK/filesystem.squashfs" >/dev/null 2>&1
unsquashfs -q -d "$ROOT" "$WORK/filesystem.squashfs" >/dev/null 2>&1

sec() { echo; echo "===== $* ====="; }

sec "image"
du -sh "$ROOT" 2>/dev/null
ls -l "$ROOT/boot"/vmlinuz* "$ROOT/boot"/initrd* 2>/dev/null | awk '{print $5, $9}'

sec "bootloader kernel command line"
sed -n 's/.*append \(.*\)/\1/p' "$ROOT"/../*.cfg 2>/dev/null | head -3
ls "$ROOT/boot/grub" 2>/dev/null

sec "lightdm config"
Ls=$(find "$ROOT/etc/lightdm" -type f 2>/dev/null)
for f in $Ls; do echo "--- $f"; cat "$f"; done

sec "lightdm seat / displays"
ls -l "$ROOT"/usr/share/xsessions/ 2>/dev/null

sec "live-config scripts"
ls "$ROOT"/usr/lib/live/config/ 2>/dev/null | head -40
echo "--- autologin related"
grep -ril autologin "$ROOT"/usr/lib/live/config/ 2>/dev/null | head

sec "accounts (no hashes)"
awk -F: '{printf "user %s uid=%s shell=%s pw=%s\n", $1, $3, $7, ($2==""?"EMPTY":($2=="!"?"LOCKED":"SET"))}' \
	"$ROOT/etc/passwd" > /dev/null
awk -F: 'NR==FNR{split($0,a,":"); pw[a[1]]=a[2]; next}
	{printf "user %-12s uid=%-5s shell=%-22s pw=%s\n", $1, $3, $7,
	 (pw[$1]=="")?"EMPTY":((pw[$1]=="!"||pw[$1]=="*")?"LOCKED":"SET")}' \
	"$ROOT/etc/shadow" "$ROOT/etc/passwd"

sec "enabled units"
ls -l "$ROOT/etc/systemd/system/multi-user.target.wants/" 2>/dev/null
ls -l "$ROOT/etc/systemd/system/graphical.target.wants/" 2>/dev/null

sec "key packages"
for pkg in live-boot live-config live-config-systemd live-tools user-setup \
	   sudo lightdm \
	   lightdm-gtk-greeter i3 i3-wm xfce4-panel thunar firefox-esr falkon \
	   calamares calamares-settings-debian xorg xserver-xorg-video-intel \
	   pipewire wireplumber network-manager zram-tools; do
	if grep -q "^Package: $pkg\$" "$ROOT/var/lib/dpkg/status" 2>/dev/null; then
		echo "present: $pkg"
	else
		echo "MISSING: $pkg"
	fi
done
echo "installed package count: $(grep -c '^Package: ' "$ROOT/var/lib/dpkg/status" 2>/dev/null)"

sec "session and helper files"
ls -l "$ROOT"/usr/local/bin/ "$ROOT"/usr/local/sbin/ 2>/dev/null
echo "--- sudoers"
cat "$ROOT/etc/sudoers.d/90-hunter-live" 2>/dev/null

sec "skel"
ls -la "$ROOT/etc/skel" 2>/dev/null | head -20

sec "autostart"
ls "$ROOT/etc/xdg/autostart/" 2>/dev/null

sec "sizes of the big payloads"
du -sh "$ROOT/usr/lib/firefox-esr" "$ROOT/usr/lib/x86_64-linux-gnu/qt6" \
	"$ROOT/usr/lib/x86_64-linux-gnu/libQt6WebEngineCore.so.6" 2>/dev/null

sec "os-release"
cat "$ROOT/etc/os-release" 2>/dev/null
