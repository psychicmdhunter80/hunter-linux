#!/usr/bin/env bash
# Install Hunter Linux to a virtual disk and then boot the installed system.
#
#   install-test.sh <iso> <work-directory> [bios|uefi] <python>
#
# Phase 1 boots the live ISO with an empty 20 GiB virtio disk attached and lets
# tools/ci/install-test.py drive Calamares.  Phase 2 boots that disk on its own
# and screenshots the result.  All evidence lands in the work directory.
set -uo pipefail

ISO="${1:?usage: install-test.sh <iso> <workdir> [bios|uefi] <python>}"
WORK="${2:?work directory required}"
MODE="${3:-uefi}"
PYTHON="${4:-python3}"

mkdir -p "$WORK"
DISK="$WORK/disk.qcow2"
RESULT="$WORK/result.txt"
: > "$RESULT"

if [ -w /dev/kvm ]; then ACCEL="kvm"; else ACCEL="tcg"; fi
echo "accelerator: $ACCEL" >> "$RESULT"
echo "mode: $MODE" >> "$RESULT"

firmware_args() {
	if [ "$MODE" != "uefi" ]; then
		return 0
	fi
	local code="" vars=""
	for candidate in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd; do
		[ -f "$candidate" ] && code="$candidate" && break
	done
	for candidate in /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd; do
		[ -f "$candidate" ] && vars="$candidate" && break
	done
	[ -n "$code" ] && [ -n "$vars" ] || { echo "FAIL: OVMF missing" | tee -a "$RESULT"; exit 0; }
	cp "$vars" "$WORK/OVMF_VARS.fd"
	echo "firmware: $code" >> "$RESULT"
	printf '%s\n' -machine q35 \
		-drive "if=pflash,format=raw,readonly=on,file=$code" \
		-drive "if=pflash,format=raw,file=$WORK/OVMF_VARS.fd"
}

mapfile -t FW < <(firmware_args)
if [ "$MODE" = "uefi" ] && [ "${#FW[@]}" -eq 0 ]; then
	exit 0
fi

qemu-img create -f qcow2 "$DISK" 20G >/dev/null

COMMON=(-m 3072 -smp 2 -accel "$ACCEL" -vga std -device usb-tablet
        -monitor "unix:$WORK/monitor.sock,server,nowait"
        -no-reboot -display none)

start_guest() {
	local serial="$1" boot=()
	shift
	if [ "$MODE" != "uefi" ]; then boot=(-boot d); fi
	qemu-system-x86_64 "${COMMON[@]}" "${FW[@]}" "${boot[@]}" \
		-serial "file:$serial" -vnc 127.0.0.1:1 "$@" \
		> "$WORK/qemu.log" 2>&1 &
	echo $!
}

echo "--- phase 1: install to disk ---" | tee -a "$RESULT"
QPID=$(start_guest "$WORK/serial-install.log" \
	-cdrom "$ISO" \
	-drive "file=$DISK,if=virtio,format=qcow2,cache=writeback")

export VNC_ADDRESS=127.0.0.1::5901
export HUNTER_PASSWORD="${HUNTER_PASSWORD:-huntertest}"
if ! "$PYTHON" "$(dirname "$0")/install-test.py" install "$WORK/install"; then
	echo "install automation: FAILED" | tee -a "$RESULT"
fi
kill "$QPID" 2>/dev/null || true
sleep 3

echo "--- installed disk contents ---" >> "$RESULT"
sudo modprobe nbd max_part=16 2>/dev/null || true
if sudo qemu-nbd -c /dev/nbd0 "$DISK" 2>/dev/null; then
	sleep 3
	sudo partx -u /dev/nbd0 2>/dev/null || true
	lsblk /dev/nbd0 >> "$RESULT" 2>&1
	for part in /dev/nbd0p*; do
		[ -e "$part" ] || continue
		type=$(sudo blkid -o value -s TYPE "$part" 2>/dev/null)
		echo "partition $part filesystem: ${type:-unknown}" >> "$RESULT"
	done
	sudo qemu-nbd -d /dev/nbd0 >/dev/null 2>&1
else
	echo "note: could not inspect the disk image with nbd" >> "$RESULT"
fi

echo "--- phase 2: boot the installed system ---" | tee -a "$RESULT"
QPID=$(start_guest "$WORK/serial-installed.log" \
	-drive "file=$DISK,if=virtio,format=qcow2,cache=writeback")
if ! "$PYTHON" "$(dirname "$0")/install-test.py" verify "$WORK/installed"; then
	echo "installed-boot automation: FAILED" | tee -a "$RESULT"
fi
kill "$QPID" 2>/dev/null || true

echo "--- summary ---" >> "$RESULT"
ls -1 "$WORK"/install/*.png 2>/dev/null | wc -l | sed 's/^/install screenshots: /' >> "$RESULT"
ls -1 "$WORK"/installed/*.png 2>/dev/null | wc -l | sed 's/^/installed screenshots: /' >> "$RESULT"
grep -ciE "Reached target graphical" "$WORK"/serial-installed.log 2>/dev/null \
	| sed 's/^/installed graphical target hits: /' >> "$RESULT"
cat "$RESULT"
