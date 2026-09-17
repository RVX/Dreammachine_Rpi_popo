# PCM5102A bring-up and acceptance test

Use this procedure on each DREAMMACHINE unit before testing the TPA3118D2
amplifier. Leave the amplifier outputs and speakers disconnected.

## Prerequisites

- Custom shield fully seated on the powered-off Raspberry Pi 4.
- Common ground and the shield power rails already verified.
- No external 3.3 V supply connected while the Raspberry Pi is installed.
- SSH enabled, or a local terminal available on the Pi.
- Legacy `dreammachine-led.service` stopped; it currently uses GPIO16/17,
  which are reserved for communication with the RP2350B on this shield.

## Configure the DAC

From the repository on the Pi:

```sh
sudo systemctl disable --now dreammachine-led.service 2>/dev/null || true
bash setup/01_audio_dac.sh
sudo reboot
```

After reboot, run the script again. It detects the ALSA card, makes it the
default output, and plays a quiet sequence: left, right, left, right.

```sh
cd /home/sjc/dreammachine
bash setup/01_audio_dac.sh --stop-reaper
```

`--stop-reaper` sends the current user's REAPER process a normal termination
signal so ALSA can open the DAC exclusively. Save any project changes first.

Expected results:

- `aplay -l` contains `sndrpihifiberry` or `HifiBerry DAC`.
- The script exits successfully and reports `DAC test completed`.
- With an oscilloscope, GPIO18 has BCK, GPIO19 has LRCK, and GPIO21 has data.
- `OUTL` and `OUTR` show a centered 1 kHz waveform during their respective
  half-second test intervals.
- Both outputs return near their quiet common-mode level after playback.

The generated tone is 48 kHz, 16-bit stereo, 1 kHz at -30 dBFS. Do not judge
speaker volume at this stage; this test verifies the digital bus and DAC only.

## Observe the DAC before powering the amplifier

Keep the amplifier 12 V rail off. Connect the oscilloscope ground clip to a
shield GND point, then use a 10x probe on these large 1206 capacitor pads:

- Left DAC output (`OUTL`): pad 1 of C65 or pad 1 of C68.
- Right DAC output (`OUTR`): pad 1 of C66 or pad 1 of C67.

Pad 1 is the DAC side of each coupling capacitor. Do not use the speaker output
connector as a scope reference; the TPA3118 outputs are bridge-tied and neither
speaker terminal is ground.

Run the longer measurement waveform:

```sh
bash setup/01_audio_dac.sh --stop-reaper --probe
```

It produces 1 kHz at -12 dBFS for five seconds on the left, then five seconds
on the right, repeated three times. A PCM5102A with nominal 2.1 Vrms full-scale
output should show approximately 0.53 Vrms, or 1.5 Vpp, on the active channel.
The inactive channel should remain near zero. A multimeter in AC-voltage mode
may show the RMS level, but an oscilloscope is the more reliable test.

For small or difficult probe points, use the two-minute mode. It holds each
channel for 30 seconds and repeats left/right twice:

```sh
bash setup/01_audio_dac.sh --stop-reaper --probe-long
```

## Troubleshooting

If the ALSA card is absent:

```sh
grep -E 'dtparam=audio|dtoverlay=hifiberry-dac' /boot/firmware/config.txt
dmesg | grep -iE 'hifiberry|pcm5102|snd'
aplay -l
```

Confirm the boot configuration contains exactly one active
`dtoverlay=hifiberry-dac` line and `dtparam=audio=off`, then reboot.

If ALSA plays without error but there is no analog waveform, probe GPIO18,
GPIO19, and GPIO21 first. Digital activity there isolates the fault to DAC
power, soldering, mute/configuration pins, or the analog output network.

## Reference-unit diagnostic checkpoint

Testing paused on `sjcdm1` on 2026-09-17 with the amplifier shut down.

- ALSA card 2 (`snd_rpi_hifiberry_dac`) opens and plays 48 kHz stereo without
  an error.
- Raspberry Pi GPIO18, GPIO19, and GPIO21 are assigned to PCM clock, frame
  sync, and data.
- No analog waveform was observed at C68 pad 1 (`OUTL`) or C66 pad 1 (`OUTR`).
- The production netlist shows `/Soft_Mute` connected only to U7 pin 17
  (`XSMT`), with no pull-up or controller connection.
- PCM5102A `XSMT` low means mute; TI permits tying it directly to AVDD when
  external mute control is not required.

Reference measurements on 2026-09-17:

- `+3.3VDAC` at C63 pad 1: 3.2 V, pass.
- `LDOO` at C64 pad 1: 1.72 V, pass.
- `VNEG` at C60 pad 1: -3.2 V, pass.
- U7 pin 17 (`XSMT`): unconnected/floating, fail.

## Mandatory XSMT rework

> Do not expect analog output from an unreworked shield. The production PCB
> leaves PCM5102A U7 pin 17 (`XSMT`) floating. `XSMT` must be high to unmute.

TI states that `XSMT` may be connected directly to AVDD when external soft-mute
control is not required. On this board AVDD is `+3.3VDAC`.

1. Mute/shut down IC1 and shut down the Raspberry Pi.
2. Disconnect external 12 V, Raspberry Pi USB-C, RP2350 USB-C, speaker, scope,
  and every other cable.
3. Verify all rails are below 0.1 V.
4. Under magnification, identify U7 pin 17. U7 is the PCM5102A TSSOP-20; pin 17
  is on the right side and carries the otherwise isolated `/Soft_Mute` net.
5. Connect U7 pin 17 to `+3.3VDAC` with a short insulated wire. C63 pad 1 is a
  verified `+3.3VDAC` attachment point. C63 pad 2 is GND; do not confuse them.
6. Inspect for bridges to adjacent U7 pins 16 (`FMT`, GND) and 18 (`LDOO`,
  approximately 1.8 V).
7. Before power-up, verify continuity from U7 pin 17 to C63 pad 1 and no short
  from pin 17 to GND.
8. Power from Raspberry Pi USB-C only and verify U7 pin 17 is approximately
  3.3 V.
9. Keep IC1 shut down and repeat the DAC scope test at C68 pad 1 (`OUTL`) and
  C66 pad 1 (`OUTR`).

Do not connect XSMT to `+12V`, `VSYSDAC`, `VNEG`, `LDOO`, or the separate
RP2350 `3V3` rail. Use the DAC-domain `+3.3VDAC` rail.

### Five-shield XSMT record

| Shield | Pin 17 to +3.3VDAC | No adjacent bridge | Powered XSMT voltage | OUTL/OUTR waveform | Technician/date |
| --- | --- | --- | --- | --- | --- |
| 1 / sjcdm1 | pass | pass | 3.3 V pass | clean L/R pass | 2026-09-17 |
| 2 | pending | pending | pending | pending |  |
| 3 | pending | pending | pending | pending |  |
| 4 | pending | pending | pending | pending |  |
| 5 | pending | pending | pending | pending |  |

Resume with a signal generator or oscilloscope and measure, in order:

1. `+3.3VDAC` relative to GND.
2. U7 pin 17 (`XSMT`) relative to GND; it must be near 3.3 V to unmute.
3. U7 pin 18 (`LDOO`), expected approximately 1.8 V.
4. I2S BCK at U7 pin 13, LRCK at pin 15, and DIN at pin 14 during playback.
5. U7 pin 6 (`OUTL`) and pin 7 (`OUTR`) before the 470 Ω output resistors.

Do not change C65/C67 or raise speaker-test level until these measurements
locate where the signal disappears.

Final reference result: after connecting XSMT to `+3.3VDAC`, clean 1 kHz
waveforms were observed alternating at C68 pad 1 (`OUTL`) and C66 pad 1
(`OUTR`). The PCM5102A DAC path is accepted on shield 1.

## Record per unit

| Unit | Hostname | ALSA card | BCK/LRCK/data | OUTL | OUTR | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | sjcdm1 | card 2, pass | not measured | not measured | not measured | software pass |
| 2 |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |
| 4 |  |  |  |  |  |  |
| 5 |  |  |  |  |  |  |