# Speaker test & calibration suite

Synthesizes a full set of high-quality WAV test signals (24-bit/48kHz,
`generate_speaker_test_signals.py`) for comparing the 6 candidate speakers
and choosing the one best suited to the DREAMMACHINE tremor content
(mostly very-low-frequency material — see `../../reaper/tremor_samples`).

## Why synthesized signals (not just music)

Standard speaker evaluation uses purpose-built signals rather than songs,
because each one isolates a specific driver/enclosure behavior (frequency
response, distortion, transient control, polarity, etc.) that's hard to
judge by ear from music alone. The kick-transient file is synthesized for
the same reason — a "punch" test without relying on copyrighted reference
tracks. For subjective full-mix listening, the [`reference_sounds/`](reference_sounds/)
folder alongside this script (sweep + music reference) can still be used
alongside this suite.

## Setup

```powershell
cd tools/speaker_test
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generate_speaker_test_signals.py
```

Output goes to `tools/speaker_test/output/test_signals/` plus a
`MANIFEST.md` describing every file and the ISO band-scan timestamps.
This output folder is git-ignored (regenerate anytime); only the script,
this README, requirements, and the scorecard template are committed.

## Test protocol

1. **Same amp, same position, same cable length** for every speaker — only
   the speaker under test should change between runs.
2. **Level-match first**: play `00_reference_tone_1kHz_-20dBFS.wav` and set
   the amp gain so every speaker hits the same SPL (SPL meter at listening
   position, or by ear at a consistent moderate level). Do this before any
   other comparison — loudness bias is the #1 confound in speaker A/B tests.
3. Work through the files in numeric order per speaker, filling in
   `scorecard_template.csv` as you go:
   - **01/02 noise** — overall tonal character/brightness.
   - **03 full sweep** — listen for audible dips, peaks, buzzes; note the
     approximate frequency if something stands out.
   - **04/05 bass sweeps** — note the lowest frequency that's still audible
     and clean (no port chuff/rattle). `05` matters most here since it
     matches the tremor sonification content's actual range.
   - **06 ISO band scan** — step through named bands; any rattle/buzz can
     be pinned to an exact frequency via `MANIFEST.md`'s timestamp table.
   - **07/08 impulse/square** — transient sharpness, ringing/overhang.
   - **09 polarity pulse** — should produce an outward cone push; a speaker
     wired backward will sound noticeably weaker/hollow next to a
     known-good reference at low frequencies.
   - **10 max SPL burst** — raise gain gradually (never start at max);
     note the level where distortion, rattle, or thermal compression
     appears. Important since the installation runs continuously.
   - **11 stereo LR identification** — only relevant if a speaker is used
     in a stereo pair; confirms channel wiring/balance.
   - **12 kick transient** — subjective punch/attack.
   - **13 THD probe tones** — for each frequency, step up through the
     three levels and note where distortion/buzz becomes audible (or
     analyze with a tool like REW if a measurement mic is available).
4. Compare scorecards across all 6 and rank, weighting bass extension/
   cleanliness heavily since that's the dominant content type here.
