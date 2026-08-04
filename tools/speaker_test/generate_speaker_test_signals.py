#!/usr/bin/env python3
"""
Generate a full speaker-comparison / calibration test-signal suite.

Produces synthesized, royalty-free WAV files (24-bit PCM, stereo) covering
the standard signal types used in professional speaker evaluation:
level reference, pink/white noise, full-range and bass-focused log sweeps,
ISO 1/3-octave tone bursts, impulse train, square wave, polarity pulse,
L/R channel identification, a synthesized percussive transient, and
multi-level THD probe tones.

Usage:
    python generate_speaker_test_signals.py [--outdir DIR] [--samplerate 48000] [--seed 0]
"""
import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import chirp

# ISO 266 preferred 1/3-octave center frequencies, 20 Hz - 20 kHz
ISO_THIRD_OCTAVE_BANDS = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500,
    630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000,
    10000, 12500, 16000, 20000,
]

# THD probe frequencies: sub-bass, bass, midrange, presence
THD_TEST_FREQS = [40, 100, 1000, 4000]
THD_TEST_LEVELS_DBFS = [-6, -12, -20]


def db_to_amp(db: float) -> float:
    return 10 ** (db / 20)


def fade_edges(x: np.ndarray, sr: int, fade_ms: float = 15.0) -> np.ndarray:
    """Raised-cosine fade in/out to avoid clicks at file boundaries."""
    n = int(sr * fade_ms / 1000)
    n = min(n, len(x) // 2)
    if n <= 0:
        return x
    window = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    x = x.copy()
    x[:n] *= window
    x[-n:] *= window[::-1]
    return x


def to_stereo(x: np.ndarray) -> np.ndarray:
    if x.ndim == 2:
        return x
    return np.stack([x, x], axis=1)


def normalize_peak(x: np.ndarray, target_dbfs: float = -1.0) -> np.ndarray:
    peak = np.max(np.abs(x))
    if peak == 0:
        return x
    return x * (db_to_amp(target_dbfs) / peak)


def pink_noise(n_samples: int, rng: np.random.Generator, num_sources: int = 16) -> np.ndarray:
    """Voss-McCartney pink noise (approx. -3dB/octave), no extra dependencies."""
    sources = rng.uniform(-1, 1, size=(num_sources, n_samples))
    counters = np.arange(n_samples)
    out = np.zeros(n_samples)
    for i in range(num_sources):
        step = 2 ** i
        if step > n_samples:
            break
        held = sources[i][(counters // step) * step % n_samples]
        out += held
    return out / num_sources


def white_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(-1, 1, size=n_samples)


def log_sweep(f0: float, f1: float, duration: float, sr: int) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return chirp(t, f0=f0, f1=f1, t1=duration, method="logarithmic")


def tone(freq: float, duration: float, sr: int) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


def square_wave(freq: float, duration: float, sr: int) -> np.ndarray:
    return np.sign(tone(freq, duration, sr))


def impulse_train(rate_hz: float, duration: float, sr: int) -> np.ndarray:
    n = int(sr * duration)
    out = np.zeros(n)
    step = int(sr / rate_hz)
    out[::step] = 1.0
    return out


def polarity_pulse(freq: float, sr: int) -> np.ndarray:
    """Single positive-going half-cycle - standard driver polarity check."""
    half_period = 1 / (2 * freq)
    t = np.linspace(0, half_period, int(sr * half_period), endpoint=False)
    pulse = np.sin(2 * np.pi * freq * t)
    tail = np.zeros(int(sr * 0.5))
    return np.concatenate([pulse, tail])


def kick_transient(sr: int, freq: float = 60.0, duration: float = 0.6) -> np.ndarray:
    """Synthesized percussive hit (pitch-dropping sine + noise click) - avoids
    using copyrighted reference music just for a subjective 'punch' test."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    pitch_env = freq * 4 * np.exp(-t * 18) + freq
    phase = 2 * np.pi * np.cumsum(pitch_env) / sr
    body = np.sin(phase) * np.exp(-t * 9)
    click = np.zeros_like(t)
    click_len = int(sr * 0.004)
    click[:click_len] = np.random.default_rng(1).uniform(-1, 1, click_len) * np.exp(
        -np.linspace(0, 8, click_len)
    )
    return body * 0.9 + click * 0.6


def concat_with_silence(parts, silence_dur: float, sr: int) -> np.ndarray:
    silence = np.zeros(int(sr * silence_dur))
    pieces = []
    for p in parts:
        pieces.append(p)
        pieces.append(silence)
    return np.concatenate(pieces[:-1])


def write(path: Path, x: np.ndarray, sr: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), to_stereo(x), sr, subtype="PCM_24")
    print(f"  wrote {path.relative_to(path.parents[1])}  ({len(x) / sr:.1f}s)")


def build(outdir: Path, sr: int, seed: int):
    rng = np.random.default_rng(seed)
    sig_dir = outdir / "test_signals"
    manifest = []

    def emit(name, description, x, dbfs=-6.0):
        x = fade_edges(x, sr)
        x = normalize_peak(x, dbfs)
        write(sig_dir / name, x, sr)
        manifest.append((name, description))

    print("Generating reference & calibration level tone...")
    emit(
        "00_reference_tone_1kHz_-20dBFS.wav",
        "Set/match SPL across all 6 speakers with an SPL meter or RTA before any other test.",
        tone(1000, 10, sr),
        dbfs=-20.0,
    )

    print("Generating noise signals...")
    emit(
        "01_pink_noise_30s.wav",
        "Tonal balance across the whole spectrum (equal energy per octave). Use with RTA/spectrum analyzer.",
        pink_noise(int(sr * 30), rng),
        dbfs=-14.0,
    )
    emit(
        "02_white_noise_10s.wav",
        "High-frequency extension / tweeter check (equal energy per Hz, brighter than pink).",
        white_noise(int(sr * 10), rng),
        dbfs=-14.0,
    )

    print("Generating sweeps...")
    emit(
        "03_sine_sweep_full_20Hz-20kHz_log_30s.wav",
        "Full-range frequency response, resonances, cabinet rattles/buzzes.",
        log_sweep(20, 20000, 30, sr),
        dbfs=-6.0,
    )
    emit(
        "04_sine_sweep_bass_20Hz-200Hz_log_20s.wav",
        "Low-end extension and port/cabinet resonance check.",
        log_sweep(20, 200, 20, sr),
        dbfs=-6.0,
    )
    emit(
        "05_sine_sweep_infrabass_10Hz-100Hz_log_20s.wav",
        "Matches the tremor/seismic sonification content range (see reaper/tremor_samples) - checks how low each speaker can usefully reproduce.",
        log_sweep(10, 100, 20, sr),
        dbfs=-6.0,
    )

    print("Generating ISO 1/3-octave band scan...")
    burst_dur, gap_dur = 2.0, 1.0
    bursts = [tone(f, burst_dur, sr) for f in ISO_THIRD_OCTAVE_BANDS]
    bursts = [fade_edges(b, sr, fade_ms=30) for b in bursts]
    band_scan = concat_with_silence(bursts, gap_dur, sr)
    band_scan = normalize_peak(band_scan, -6.0)
    write(sig_dir / "06_iso_third_octave_band_scan.wav", band_scan, sr)
    t_cursor = 0.0
    band_timestamps = []
    for f in ISO_THIRD_OCTAVE_BANDS:
        band_timestamps.append((f, t_cursor))
        t_cursor += burst_dur + gap_dur
    manifest.append(
        (
            "06_iso_third_octave_band_scan.wav",
            "Sequential 2s tone bursts at each ISO 1/3-octave center (20Hz-20kHz, 1s gaps) - "
            "pinpoints which exact frequency triggers a rattle/buzz/resonance. See timestamps below.",
        )
    )

    print("Generating transient/impulse tests...")
    emit(
        "07_impulse_train_2Hz_10s.wav",
        "Transient response, ringing/decay, port chuffing.",
        impulse_train(2, 10, sr),
        dbfs=-3.0,
    )
    emit(
        "08_square_wave_100Hz_10s.wav",
        "Cone/driver transient control and edge definition.",
        square_wave(100, 10, sr),
        dbfs=-6.0,
    )
    emit(
        "09_polarity_test_pulse_40Hz.wav",
        "Single positive half-cycle - confirms driver is wired in correct polarity (check with scope, mic, or by ear/feel next to another known-good speaker).",
        polarity_pulse(40, sr),
        dbfs=-1.0,
    )

    print("Generating max-level / excursion probe...")
    burst = tone(40, 3.0, sr)
    burst = fade_edges(burst, sr, fade_ms=50)
    emit(
        "10_max_spl_lowfreq_burst_40Hz.wav",
        "Short high-level 40Hz burst - listen for rattle, buzz, thermal compression, or excursion limiting at your intended max drive level (raise the amp gain step by step, do not start at max).",
        burst,
        dbfs=-1.0,
    )

    print("Generating stereo channel identification...")
    left = np.stack([tone(440, 3, sr), np.zeros(int(sr * 3))], axis=1)
    right = np.stack([np.zeros(int(sr * 3)), tone(880, 3, sr)], axis=1)
    both = np.stack([tone(440, 3, sr), tone(880, 3, sr)], axis=1)
    silence_stereo = np.zeros((int(sr * 1), 2))
    lr_test = np.concatenate([left, silence_stereo, right, silence_stereo, both])
    lr_test = normalize_peak(lr_test, -6.0)
    write(sig_dir / "11_stereo_LR_identification.wav", lr_test, sr)
    manifest.append(
        (
            "11_stereo_LR_identification.wav",
            "Left-only (440Hz) -> Right-only (880Hz) -> both together - confirms wiring/channel balance on stereo pairs.",
        )
    )

    print("Generating synthesized percussive transient...")
    emit(
        "12_kick_transient_synth.wav",
        "Synthesized kick-drum-like hit (pitch-drop sine + click) for subjective 'punch'/attack comparison without relying on copyrighted reference music.",
        np.tile(kick_transient(sr), 4),
        dbfs=-3.0,
    )

    print("Generating multi-level THD probe tones...")
    for f in THD_TEST_FREQS:
        for lvl in THD_TEST_LEVELS_DBFS:
            name = f"13_thd_probe_{f}Hz_{lvl}dBFS.wav".replace("--", "-")
            emit(
                name,
                f"{f}Hz tone at {lvl}dBFS - raise level per file and listen for audible distortion/buzz onset (or analyze THD with REW/similar).",
                tone(f, 5, sr),
                dbfs=lvl,
            )

    return manifest, band_timestamps


def write_manifest(outdir: Path, manifest, band_timestamps):
    lines = ["# Speaker test signal manifest", ""]
    for name, desc in manifest:
        lines.append(f"- **{name}** - {desc}")
    lines += ["", "## ISO 1/3-octave band scan timestamps (06_iso_third_octave_band_scan.wav)", ""]
    for f, t in band_timestamps:
        lines.append(f"- {f:>7} Hz @ {t:6.1f}s")
    (outdir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {outdir / 'MANIFEST.md'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default=str(Path(__file__).parent / "output"))
    parser.add_argument("--samplerate", type=int, default=48000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    manifest, band_timestamps = build(outdir, args.samplerate, args.seed)
    write_manifest(outdir, manifest, band_timestamps)
    print(f"\nDone. {len(manifest)} test signals in {outdir / 'test_signals'}")


if __name__ == "__main__":
    main()
