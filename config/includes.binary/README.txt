SMD LINUX 1.0
===============

A lightweight Debian 13 (trixie) desktop: Xorg + i3 + xfce4-panel.

Boot options
------------
Start SMD Linux Live
    Runs the complete system from this USB device. Nothing on the internal
    drive is touched.

Start SMD Linux Live (Safe Graphics)
    Same, with kernel mode setting disabled. Use this if the screen stays
    black or the desktop does not start on your graphics hardware.

Install SMD Linux
    Starts the same live system and opens the graphical installer (Calamares)
    automatically. You can also install later from the desktop icon
    "Install SMD Linux" or from the application menu.

Advanced Boot Options
    Verbose boot, run the system from RAM, checksum verification,
    UEFI firmware settings and "boot from the first hard disk".

Live session details
--------------------
User:      user
Password:  live        (only needed if automatic login is disabled)
sudo:      passwordless in the live session, disabled after installation

Writing this image to a USB device
----------------------------------
Linux:   sudo dd if=SMD-Linux-v1.0-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
macOS:   sudo dd if=SMD-Linux-v1.0-amd64.iso of=/dev/rdiskN bs=4m
Windows: use Rufus (DD mode) or balenaEtcher and select the ISO file.

The image boots on both legacy BIOS and UEFI machines.
