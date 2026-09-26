# RP2350B PWM/SPI Control Audit — DREAMMACHINE

**Date**: 2026-09-25
**Unit**: sjcdm4
**Status**: ✅ RESOLVED — non-blocking fades + dual-pulse sync working over SPI

## Problem Statement

Need precise, flicker-free PWM brightness control of 6 MOSFET channels (GPIO33-38) via SPI from Raspberry Pi, with the RP2350B handling all timing-critical operations (fades, patterns, generative sequences) to avoid Pi GPIO jitter.

## What Was Tried (and Failed)

### 1. Two-Byte SPI Command (0x40+ch, brightness)
**Approach**: Send `[0x41, 100]` via `xfer2()` — first byte = command, second = brightness.

**Failure modes**:
- Second byte never arrived at RP2350 (CS deasserts between bytes in `xfer2`)
- `spi_read_blocking()` for second byte blocked forever or returned garbage
- Multiple GPIOs lit randomly (command misinterpretation)

**Root cause**: RP2350 SPI slave doesn't buffer bytes across CS assertions. When Pi's `xfer2([b1, b2])` toggles CS between bytes, the second byte is lost.

### 2. 16-bit SPI Frame Mode
**Approach**: Configure SPI for 16-bit frames, send command+brightness as one word.

**Failure**: GPIO33, 35, 37 (odd channels) stuck on — likely byte order or frame alignment issue.

### 3. IRQ-Based Circular Buffer
**Approach**: SPI RX FIFO IRQ + CS edge detection to buffer bytes while CS low.

**Failure**: Nothing worked at all — IRQ handler likely not firing or CS detection broken.

### 4. Built-in Fade Commands (0x51-0x56, 0x61-0x66)
**Approach**: Single-byte command triggers RP2350-local fade sequence.

**Failure**: No fade observed — likely the blocking `sleep_ms()` loop in `fade_channel()` interfered with SPI processing, or the function crashed.

## What Works (Baseline)

**Commit c7da3e4** — single-byte commands, no PWM:
- `0x00` — all off + amp shutdown
- `0x01-0x06` — pulse channel 1-6 for 500ms
- `0x10` — chase pattern
- `0x11` — bounce pattern
- `0x12` — flash all 5x
- `0x20-0x23` — amp control (shutdown/start-muted/unmute/mute)

**Standalone fade test** (no SPI): Arduino-style fade on GPIO33 worked perfectly — proves PWM hardware is functional.

## Resolution (2026-09-25)

**Option A (non-blocking fades) implemented and verified working.**

Key insight: the RP2350 SPI slave loses the second byte of multi-byte transfers
when the Pi's `spidev.xfer2([b1, b2])` toggles CS between bytes. Solution:
**keep all commands single-byte** and let the RP2350 run the timing locally.

### Final command set (all single-byte over SPI)

| Command | Action |
| --- | --- |
| `0x00` | All MOSFETs off + amp shutdown + stop all fades |
| `0x01`-`0x06` | Pulse channel 1-6 for 500 ms (blocking, GPIO mode) |
| `0x07` | **Dual pulse AMOS1+AMOS2 together, 100 ms** (for kick-sync) |
| `0x10` | Chase pattern |
| `0x11` | Bounce pattern |
| `0x12` | Flash all 5x |
| `0x20`-`0x23` | Amp control (shutdown / start-muted / unmute / mute) |
| `0x51`-`0x56` | **Fade IN channel 1-6** (0→100% over ~1 s, non-blocking) |
| `0x61`-`0x66` | **Fade OUT channel 1-6** (100→0% over ~1 s, non-blocking) |
| `0x71`-`0x76` | Stop fade on channel 1-6 and turn off |

### How the non-blocking fades work

- `fade_start(ch, dir)` sets target/direction state; returns immediately
- `fade_update()` runs every main-loop iteration, stepping brightness every
  20 ms toward the target — SPI stays responsive during fades
- `pulse()`/`all_off()` explicitly switch pins back to GPIO mode (PWM off)
  so legacy patterns and fades can interleave cleanly

### Verified on sjcdm4

`rp2350/led_speaker_sync_test1.py` stages 1-5 all pass:
fades track tones, dual-pulse kick-sync flashes both channels simultaneously.

### Future extension path (if multi-byte commands are ever needed)

If a future feature needs true per-command brightness values (e.g. set channel
to exactly 37%), the robust route is a **PIO-based SPI slave** that captures
both bytes atomically during CS-low, since the RP2350's SPI peripheral FIFO
does not reliably deliver the second byte across CS toggles from the Pi's
spidev. Not needed for the current single-byte command set.

## Files

- `rp2350/main.c` — current firmware (restored to working state)
- `rp2350/pattern.py` — Pi-side command sender (works)
- `rp2350/led_speaker_sync_test1.py` — sync test (needs working PWM)
- `/tmp/simple_fade.c` — standalone fade proof-of-concept (works, no SPI)

## Lessons Learned

- RP2350 SPI slave is finicky with multi-byte transfers across CS toggles
- Blocking `sleep_ms()` in command handlers breaks SPI responsiveness
- USB serial is more reliable than SPI for debugging/complex commands
- Always test standalone (no SPI) first to isolate hardware vs protocol issues
