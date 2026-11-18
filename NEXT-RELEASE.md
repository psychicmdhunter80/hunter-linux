# SMD Linux - requested for the next release

Recorded during the 1.5.0 work and deliberately **not** included in 1.5.0.
Nothing here is implemented, promised or tested; it is the list to pick up next.

1. **Visible loading feedback.** Show "SMD Linux is loading..." while the
   session comes up, instead of the bare wallpaper.
2. **Correct version labels everywhere, including rendered artwork.** Hunter's
   photo of the running 1.5.0 installer shows *1.4.1* baked into the Calamares
   branding image beneath the 1.5.0 heading. The text labels are checked by
   `tools/verify-project.py`; the rendered PNG artwork is not, which is how this
   slipped through.
3. **An "Install SMD Linux" favourite on the live desktop**, directly below
   Terminal Emulator, present only in the live session and removed by the
   installer on the installed system.
4. **Numbered workspace buttons (1-4)** in place of the miniature panel
   previews.
5. **Alt+1 .. Alt+4 to switch workspaces.** Check the combination for conflicts
   against the applications' own shortcuts first; Ctrl+Alt+number is the
   approved fallback if a conflict is real.
6. **Offline HTML help** for the desktop and its shortcuts - deferred until the
   build settles.

Tiling is *not* on this list: the 1.5.0 custom tiling helper is the one Hunter
confirmed on Craig, and it stays as it is.
