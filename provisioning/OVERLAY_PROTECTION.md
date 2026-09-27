# DREAMMACHINE SD Card Corruption Protection
#
# Problem: sudden power loss during SD write = corrupted filesystem = no boot.
# Solution: overlayfs — root filesystem mounted read-only, all writes go to
# RAM (tmpfs). On reboot, RAM is wiped and the SD is back to its clean state.
#
# TRADE-OFFS:
#   - Any file changes made while running are LOST on reboot (logs, configs)
#   - POPO wavs, REAPER project saves, Telegram logs — all gone after reboot
#   - This is actually GOOD for a collector unit: always boots to known state
#
# HOW TO ENABLE (run once, needs reboot):
#   sudo raspi-config nonint enable_overlayfs
#   sudo reboot
#
# HOW TO DISABLE (if you need to make persistent changes):
#   sudo raspi-config nonint disable_overlayfs
#   sudo reboot
#
# To check if overlay is active:
#   mount | grep overlay
#   # Should show: overlay on / type overlay (ro,...)
#
# IMPORTANT: When overlay is ON, to make persistent changes:
#   1. Disable overlay, reboot
#   2. Make changes
#   3. Re-enable overlay, reboot
#
# /tmp is already tmpfs (RAM) regardless of overlay — nothing to do there.
# /home/sjc/popo/datasets/ should be symlinked to /tmp if overlay is enabled,
# so POPO wavs don't fill RAM unnecessarily (they get regenerated anyway).
