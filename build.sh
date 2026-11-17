#!/bin/sh
# SMD Linux 1.0 - build driver.
#
#   ./build.sh            build in Docker when Docker is available, else natively
#   ./build.sh docker     force a Docker build
#   ./build.sh native     force a build on this machine (Debian 13, root)
#   ./build.sh clean      remove all build artefacts
#
# The build needs: live-build (>= 1:20250505), debootstrap, xorriso,
# squashfs-tools, and root privileges.  Docker path handles this for you.
set -eu

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
MODE="${1:-auto}"
IMAGE_NAME="SMD-Linux-v1.4.1-amd64.iso"

log() { printf '\n==> %s\n' "$*"; }

clean_build() {
	# `lb clean --purge` removes chroot/, binary/, cache/ and .build/.
	# Safe to run repeatedly; it never touches config/.
	if command -v lb >/dev/null 2>&1; then
		lb clean --purge || true
	fi
	rm -rf chroot binary cache .build .lock
	rm -f ./*.iso ./*.zsync ./*.sha256 ./*.contents ./*.files ./*.packages
	rm -f ./*.hybrid.iso ./*.list.tar.gz ./*.log
}

build_native() {
	if [ "$(id -u)" -ne 0 ]; then
		echo "error: a native build must run as root (debootstrap + chroot)." >&2
		echo "       use './build.sh docker' instead if you are not on Debian." >&2
		exit 1
	fi
	for tool in lb debootstrap xorriso mksquashfs; do
		command -v "$tool" >/dev/null 2>&1 || {
			echo "error: missing build tool '$tool'." >&2
			echo "       apt-get install live-build debootstrap xorriso squashfs-tools" >&2
			exit 1
		}
	done

	log "cleaning previous build"
	clean_build

	log "building ISO (this downloads ~1.5 GB of Debian packages)"
	lb build

	if [ -f "SMD-Linux-v1.4.1-amd64.hybrid.iso" ]; then
		mv -f "SMD-Linux-v1.4.1-amd64.hybrid.iso" "${IMAGE_NAME}"
	fi
	[ -f "${IMAGE_NAME}" ] || {
		echo "error: build finished without producing ${IMAGE_NAME}" >&2
		exit 1
	}

	log "build finished: ${PROJECT_DIR}/${IMAGE_NAME}"
	sha256sum "${IMAGE_NAME}" | tee "${IMAGE_NAME}.sha256"
	ls -lh "${IMAGE_NAME}"
}

build_docker() {
	command -v docker >/dev/null 2>&1 || {
		echo "error: docker not found." >&2
		exit 1
	}
	log "building build container"
	docker build -t hunter-linux-build:1.0 -f Dockerfile .
	log "running build inside container"
	# --privileged is required: live-build mounts proc/sys/dev inside the chroot.
	docker run --rm --privileged \
		-v "${PROJECT_DIR}:/build" \
		-w /build \
		-e HUNTER_MIRROR="${HUNTER_MIRROR:-}" \
		hunter-linux-build:1.0 \
		sh -c 'HUNTER_MIRROR=${HUNTER_MIRROR:-http://deb.debian.org/debian/} ./build.sh native'
}

case "${MODE}" in
	auto)
		if command -v docker >/dev/null 2>&1; then
			build_docker
		else
			build_native
		fi
		;;
	docker) build_docker ;;
	native) build_native ;;
	clean) clean_build ;;
	*)
		echo "usage: $0 [auto|docker|native|clean]" >&2
		exit 2
		;;
esac
