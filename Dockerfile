# Build environment for SMD Linux 1.0.
#
# Debian 13 (trixie) is the same release the image is built from, so the
# live-build version in the container is the one the configuration was
# written against.
FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
	live-build \
	debootstrap \
	xorriso \
	squashfs-tools \
	rsync \
	ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /build

# The project directory is bind-mounted by build.sh; nothing is copied in.
CMD ["sh", "./build.sh", "native"]
