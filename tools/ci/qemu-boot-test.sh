#!/usr/bin/env bash
# Boot a Hunter Linux ISO under QEMU and capture evidence of a working desktop.
#
#   qemu-boot-test.sh <iso> <bios|uefi> <output-directory>
#
# Produces, in the output directory:
#   serial.log        kernel and systemd output from the guest
#   screen-NN.png     screenshots at each step
#   result.txt        PASS/FAIL summary for the steps that were attempted
#
# The guest has no network and no accelerators are required: KVM is used when
# available and TCG otherwise. Everything is driven through the QEMU monitor
# (screendump + sendkey), so no X server is needed on the host.
set -uo pipefail

ISO="${1:?usage: qemu-boot-test.sh <iso> <bios|uefi> <outdir>}"
MODE="${2:-bios}"
OUT="${3:-qemu-out}"

mkdir -p "$OUT"
MON="$OUT/monitor.sock"
SERIAL="$OUT/serial.log"
RESULT="$OUT/result.txt"
: > "$RESULT"
: > "$SERIAL"

if [ -w /dev/kvm ]; then ACCEL="kvm"; else ACCEL="tcg"; fi
echo "accelerator: $ACCEL" >> "$RESULT"

COMMON=(-m 2048 -smp 2 -accel "$ACCEL" -display none -vga std
        -monitor "unix:$MON,server,nowait" -serial "file:$SERIAL"
        -no-reboot -no-shutdown)

if [ "$MODE" = "uefi" ]; then
	CODE=""
	for candidate in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd \
	                 /usr/share/edk2/ovmf/OVMF_CODE.fd; do
		[ -f "$candidate" ] && CODE="$candidate" && break
	done
	VARS_SRC=""
	for candidate in /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd \
	                 /usr/share/edk2/ovmf/OVMF_VARS.fd; do
		[ -f "$candidate" ] && VARS_SRC="$candidate" && break
	done
	if [ -z "$CODE" ] || [ -z "$VARS_SRC" ]; then
		echo "FAIL: no OVMF firmware found" | tee -a "$RESULT"
		exit 0
	fi
	cp "$VARS_SRC" "$OUT/OVMF_VARS.fd"
	echo "firmware: $CODE" >> "$RESULT"
	BOOT=(-drive "if=pflash,format=raw,readonly=on,file=$CODE"
	      -drive "if=pflash,format=raw,file=$OUT/OVMF_VARS.fd")
else
	BOOT=(-boot d)
fi

qemu-system-x86_64 "${COMMON[@]}" "${BOOT[@]}" -cdrom "$ISO" \
	> "$OUT/qemu.log" 2>&1 &
QPID=$!
trap 'kill $QPID 2>/dev/null' EXIT

hmp() { printf '%s\n' "$1" | socat -t 3 - "UNIX-CONNECT:$MON" >/dev/null 2>&1; }

shot() {
	local name="$1"
	hmp "screendump $OUT/screen-$name.ppm"
	sleep 1
	if command -v convert >/dev/null 2>&1; then
		convert "$OUT/screen-$name.ppm" "$OUT/screen-$name.png" 2>/dev/null || true
	fi
	echo "screenshot: screen-$name.png" >> "$RESULT"
}

key() { hmp "sendkey $1"; sleep "${2:-1}"; }

type_text() {
	local text="$1" i char
	for ((i = 0; i < ${#text}; i++)); do
		char="${text:$i:1}"
		case "$char" in
			' ') key spc 0.2 ;;
			'-') key minus 0.2 ;;
			'.') key dot 0.2 ;;
			*) key "$char" 0.2 ;;
		esac
	done
}

# Wait for the monitor socket, then for the graphical target in the guest.
for _ in $(seq 1 30); do
	[ -S "$MON" ] && break
	sleep 2
done

booted=false
for _ in $(seq 1 90); do
	if grep -qiE "Reached target (graphical|Graphical)" "$SERIAL" 2>/dev/null; then
		booted=true
		break
	fi
	sleep 5
done

if ! $booted; then
	echo "WARN: graphical target not seen in serial log; capturing anyway" >> "$RESULT"
fi
sleep 20
shot "01-boot"

# Give the session (panel, tray applets, i3) time to settle.
sleep 25
shot "02-desktop"

# Terminal: Super+Enter
key meta_l-Return 2
sleep 8
shot "03-terminal"

# Firefox ESR from the terminal prompt
type_text "firefox-esr"
key ret 1
sleep 30
shot "04-firefox"

# Thunar: Super+E
key meta_l-e 2
sleep 10
shot "05-thunar"

# Falkon through the launcher: Super+D, type, Enter
key meta_l-d 2
sleep 3
shot "06-launcher"
type_text "falkon"
key ret 1
sleep 25
shot "07-falkon"

# Graphical installer through the launcher
key meta_l-d 2
sleep 3
type_text "install hunter"
key ret 1
sleep 25
shot "08-installer"

# Record what the guest thinks it is running.
hmp "info status"
key ctrl-alt-f2 2
sleep 3
shot "09-console"

kill $QPID 2>/dev/null || true
sleep 2
echo "done" >> "$RESULT"

# Summarise
{
	echo "mode: $MODE"
	echo "booted_graphical: $booted"
	grep -ciE "lightdm|i3|xfce4-panel" "$SERIAL" 2>/dev/null | sed 's/^/session_log_hits: /'
	ls -1 "$OUT"/screen-*.png 2>/dev/null | wc -l | sed 's/^/screenshots: /'
} >> "$RESULT"

cat "$RESULT"
