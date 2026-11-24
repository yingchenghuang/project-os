"""80s light jazz-fusion score (120 BPM, F major, 120 s) synthesised with numpy.

Sections follow the animation: 0-24 s day aerial, 24-46 ground orbit,
46-70 dusk / lights on, 70-100 night interior (one chime per pendant
lighting up, 72-82 s), 100-120 night outro.
usage: python3 tools/music.py out.wav
"""
import sys
import numpy as np
import wave

SR = 44100
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
DUR = 120.0
N = int(SR * DUR)
rng = np.random.default_rng(1960)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env_adsr(n, a, d, s, r, sustain_len=None):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    sl = n - a - d - r if sustain_len is None else int(sustain_len * SR)
    sl = max(0, sl)
    e = np.concatenate([np.linspace(0, 1, max(a, 1)), np.linspace(1, s, max(d, 1)), np.full(sl, s), np.linspace(s, 0, max(r, 1))])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def onepole_lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x); acc = 0.0
    # vectorised via lfilter-like recursion in chunks
    from scipy.signal import lfilter  # noqa
    return lfilter([1 - a], [1, -a], x)


def add(buf, start_s, sig, gain=1.0, pan=0.0):
    i = int(start_s * SR)
    if i >= buf.shape[1]:
        return
    sig = sig[: buf.shape[1] - i]
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    buf[0, i:i + len(sig)] += sig * gain * l
    buf[1, i:i + len(sig)] += sig * gain * r


# ------------------------------------------------------------ instruments
def kick():
    n = int(0.45 * SR); t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7) + 0.3 * np.exp(-t * 300) * rng.standard_normal(n) * 0.2


def snare():
    n = int(0.35 * SR); t = np.arange(n) / SR
    from scipy.signal import butter, lfilter
    b, a = butter(2, [1200 / (SR / 2), 7000 / (SR / 2)], 'band')
    noise = lfilter(b, a, rng.standard_normal(n)) * np.exp(-t * 16)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return 0.9 * noise + 0.5 * tone


def rim():
    n = int(0.08 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 1700 * t) + 0.5 * np.sin(2 * np.pi * 820 * t)) * np.exp(-t * 90)


def hat(open_=False):
    n = int((0.32 if open_ else 0.06) * SR); t = np.arange(n) / SR
    from scipy.signal import butter, lfilter
    b, a = butter(2, 7000 / (SR / 2), 'high')
    return lfilter(b, a, rng.standard_normal(n)) * np.exp(-t * (9 if open_ else 70))


def clap():
    n = int(0.25 * SR); t = np.arange(n) / SR
    from scipy.signal import butter, lfilter
    b, a = butter(2, [900 / (SR / 2), 4000 / (SR / 2)], 'band')
    x = lfilter(b, a, rng.standard_normal(n))
    e = np.exp(-t * 25)
    for d in (0.0, 0.011, 0.022):
        e += np.where(t >= d, np.exp(-(t - d) * 180), 0)
    return x * e * 0.5


def synth_bass(m, dur):
    n = int(dur * SR); t = np.arange(n) / SR; f = mtof(m)
    saw = 2 * ((t * f) % 1) - 1
    sq = np.sign(np.sin(2 * np.pi * f * t))
    x = 0.6 * saw + 0.4 * sq + 0.6 * np.sin(2 * np.pi * f * t)
    from scipy.signal import lfilter
    # envelope-swept lowpass (piecewise)
    out = np.zeros(n); seg = 512
    zi = np.zeros(1)
    for i in range(0, n, seg):
        fc = 180 + 1400 * np.exp(-t[i] * 14)
        a = np.exp(-2 * np.pi * fc / SR)
        y, zi = lfilter([1 - a], [1, -a], x[i:i + seg], zi=zi)
        out[i:i + seg] = y
    out = lfilter([1 - np.exp(-2 * np.pi * 900 / SR)], [1, -np.exp(-2 * np.pi * 900 / SR)], out)
    return out * env_adsr(n, 0.004, 0.12, 0.65, 0.05)


def rhodes(m, dur, vel=1.0):
    n = int((dur + 1.2) * SR); t = np.arange(n) / SR; f = mtof(m)
    idx = (1.8 * vel) * np.exp(-t * 5) + 0.25
    mod = np.sin(2 * np.pi * f * t) * idx
    tine = np.sin(2 * np.pi * f * 7.0 * t) * 0.08 * vel * np.exp(-t * 18)
    x = np.sin(2 * np.pi * f * t + mod) + tine
    e = np.exp(-t * 1.1) * np.where(t < dur, 1.0, np.exp(-(t - dur) * 9))
    trem = 1 + 0.18 * np.sin(2 * np.pi * 4.6 * t)
    return x * e * trem * vel


def pad(ms, dur):
    n = int((dur + 1.5) * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for m in ms:
        for det in (-0.12, 0.0, 0.11):
            f = mtof(m + det)
            x += 2 * ((t * f + rng.random()) % 1) - 1
    from scipy.signal import lfilter
    a = np.exp(-2 * np.pi * 1300 / SR)
    x = lfilter([1 - a], [1, -a], x)
    x = lfilter([1 - a], [1, -a], x)
    e = env_adsr(n, 0.6, 0.4, 0.8, 1.4, sustain_len=max(0, dur - 1.0))
    return x * e / (3 * len(ms))


def lead(m, dur, vel=1.0):
    """FM 'synth-sax' with delayed vibrato."""
    n = int((dur + 0.25) * SR); t = np.arange(n) / SR; f = mtof(m)
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.18) / 0.2, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    idx = 1.3 + 0.9 * np.exp(-t * 6)
    x = np.sin(ph + idx * np.sin(ph * 1.0) + 0.4 * np.sin(ph * 2.0))
    breath = rng.standard_normal(n) * 0.03 * np.exp(-t * 12)
    return (x + breath) * env_adsr(n, 0.03, 0.15, 0.75, 0.18, sustain_len=max(0, dur - 0.2)) * vel


def chime(m):
    n = int(2.8 * SR); t = np.arange(n) / SR; f = mtof(m)
    x = np.sin(2 * np.pi * f * t + 1.2 * np.exp(-t * 3) * np.sin(2 * np.pi * f * 3.5 * t))
    return x * np.exp(-t * 2.2) * np.minimum(1, t * 400)


# ------------------------------------------------------------ harmony
# rootless voicings (midi), bass roots
A_SEC = [('Gm9', 43, [58, 62, 65, 69]), ('C13', 48, [58, 64, 69, 74]), ('Fmaj9', 41, [57, 60, 64, 67]), ('Dm9', 50, [57, 60, 64, 65])]
B_SEC = [('Bbmaj9', 46, [57, 60, 62, 65]), ('Am7', 45, [55, 60, 64, 67]), ('Gm7', 43, [58, 62, 65, 67]), ('C7sus', 48, [58, 62, 65, 67])]


def chord_at(bar):
    sec = A_SEC if (bar // 4) % 3 != 2 else B_SEC
    return sec[bar % 4]


# melody phrases: (beat offset in 2-bar phrase, dur beats, midi)
PHRASES = [
    [(0.5, 0.5, 70), (1, 0.5, 72), (1.5, 1.0, 74), (3, 0.5, 72), (3.5, 1.5, 70), (5.5, 0.5, 69), (6, 1.5, 72)],
    [(0, 0.5, 77), (0.5, 0.5, 76), (1, 1.0, 74), (2.5, 0.5, 72), (3, 1.0, 69), (4.5, 0.5, 67), (5, 0.5, 69), (5.5, 2.0, 72)],
    [(0.5, 0.5, 74), (1, 0.5, 76), (1.5, 0.5, 77), (2, 1.5, 79), (4, 0.5, 77), (4.5, 0.5, 76), (5, 0.5, 74), (5.5, 2.0, 72)],
    [(0, 1.0, 81), (1.5, 0.5, 79), (2, 0.5, 77), (2.5, 1.0, 76), (4, 0.5, 74), (4.5, 0.5, 72), (5, 2.5, 74)],
]


def build():
    from scipy.signal import fftconvolve
    dry = np.zeros((2, N)); wet = np.zeros((2, N)); drums_gate = np.zeros((2, N))
    K, Sn, R, HC, HO, CL = kick(), snare(), rim(), hat(), hat(True), clap()
    swing = 0.07  # 16th swing (in beats)
    nbars = int(DUR / BAR)
    for bar in range(nbars):
        t0 = bar * BAR
        name, root, voic = chord_at(bar)
        sec = 0 if t0 < 24 else 1 if t0 < 46 else 2 if t0 < 70 else 3 if t0 < 100 else 4
        last = bar == nbars - 1
        # ---- drums
        full = (sec in (1, 4)) or (sec == 0 and bar >= 8)
        light = sec == 2 or (sec == 0 and 4 <= bar < 8)
        night = sec == 3
        if not last:
            for s16 in range(16):
                beat = s16 / 4 + (swing if s16 % 2 else 0)
                ts = t0 + beat * BEAT
                if full or light or (sec == 0 and bar >= 2) or night:
                    if not (night and s16 % 2):
                        g = 0.11 if s16 % 4 == 0 else 0.07
                        if night:
                            g *= 0.6
                        add(dry, ts, HC, g, 0.35)
                if s16 == 14 and (full) and bar % 2 == 1:
                    add(dry, ts, HO, 0.08, 0.35)
            if full:
                for b in (0, 1.5, 2.5) if bar % 2 == 0 else (0, 2.0, 2.75):
                    add(dry, t0 + b * BEAT, K, 0.85)
                for b in (1, 3):
                    add(dry, t0 + b * BEAT, Sn, 0.42, -0.05); add(drums_gate, t0 + b * BEAT, Sn, 0.5)
                    add(dry, t0 + b * BEAT, CL, 0.25, 0.1)
            elif light:
                for b in (0, 2.5):
                    add(dry, t0 + b * BEAT, K, 0.55)
                for b in (1, 3):
                    add(dry, t0 + b * BEAT + 0.5 * BEAT * (b == 3), R, 0.22, -0.2)
            elif night and bar % 2 == 0:
                add(dry, t0, K, 0.4)
                add(dry, t0 + 2 * BEAT, R, 0.16, -0.2); add(wet, t0 + 2 * BEAT, R, 0.1)
        # ---- bass
        if (sec == 0 and bar >= 4) or sec in (1, 2, 4):
            pat = [(0, 0.75, 0), (1.5, 0.5, 12), (2, 0.5, 7), (2.75, 0.5, 0), (3.5, 0.5, 10)] if sec != 2 else [(0, 1.5, 0), (2, 1.0, 7), (3.5, 0.5, 0)]
            if last:
                pat = [(0, 3.5, 0)]
            for b, d, iv in pat:
                add(dry, t0 + b * BEAT, synth_bass(root + iv - 12 if root > 45 else root + iv, d * BEAT), 0.38)
        elif sec == 3:
            add(dry, t0, synth_bass(root - 12 if root > 45 else root, 3.2 * BEAT), 0.3)
        # ---- rhodes comping
        if sec in (0, 1, 4) or (sec == 2):
            hits = [(0, 1.2), (1.5, 0.4), (2.75, 1.0)] if sec in (1, 4) else [(0, 3.5)]
            if last:
                hits = [(0, 6.0)]
            for b, d in hits:
                for k, m in enumerate(voic):
                    s = rhodes(m, d * BEAT, 0.8 if sec != 0 else 0.6)
                    add(dry, t0 + b * BEAT + k * 0.012, s, 0.085, -0.25 + 0.15 * k)
                    add(wet, t0 + b * BEAT + k * 0.012, s, 0.04)
        elif sec == 3:
            # night: slow arpeggiated electric piano
            for k, m in enumerate(voic + [voic[1] + 12]):
                s = rhodes(m, 2.5 * BEAT, 0.5)
                add(dry, t0 + k * 0.75 * BEAT, s, 0.07, -0.4 + 0.2 * k); add(wet, t0 + k * 0.75 * BEAT, s, 0.06)
        # ---- pad
        if sec in (2, 3) or (sec == 4 and not last):
            p = pad([m - 12 for m in voic[:3]] + [voic[3]], BAR)
            add(dry, t0, p, 0.22 if sec != 4 else 0.12); add(wet, t0, p, 0.12)
        # ---- lead melody
        if sec in (1, 4) and not last:
            ph = (bar - (12 if sec == 1 else 50)) // 2
            if (bar % 2 == 0) and bar + 1 < nbars:
                phrase = PHRASES[ph % len(PHRASES)]
                shift = 0 if sec == 1 else 0
                for b, d, m in phrase:
                    s = lead(m + shift, d * BEAT, 0.9)
                    add(dry, t0 + b * BEAT, s, 0.16, 0.15); add(wet, t0 + b * BEAT, s, 0.08)
                    add(wet, t0 + b * BEAT + 0.375, s, 0.05)  # dotted-8th echo
        if sec == 2 and bar % 4 == 1:
            # dusk: muted lead answer
            for b, d, m in [(0.5, 0.5, 72), (1, 0.5, 74), (1.5, 2.0, 77), (4, 0.5, 76), (4.5, 2.5, 74)]:
                s = lead(m, d * BEAT, 0.6)
                add(dry, t0 + b * BEAT, s, 0.1, 0.2); add(wet, t0 + b * BEAT, s, 0.1)
    # ---- light cues: neon on (52-57 s) swell, one chime per pendant (72-82 s), accent (86 s)
    pent = [65, 67, 69, 72, 74, 77, 79, 81, 84, 86]
    for i in range(30):
        ts = 72 + i * (10 / 30)
        m = pent[(i * 3) % len(pent)] + (12 if i % 7 == 6 else 0)
        add(dry, ts, chime(m), 0.07, -0.6 + 1.2 * (i / 29)); add(wet, ts, chime(m), 0.07)
    sw = pad([53, 60, 65, 69, 72], 6.0)
    add(dry, 52, sw, 0.18); add(wet, 52, sw, 0.18)
    for k, m in enumerate([65, 69, 72, 76, 79]):
        add(wet, 86 + k * 0.09, chime(m), 0.08); add(dry, 86 + k * 0.09, chime(m), 0.05, -0.3 + 0.15 * k)
    # ---- reverbs
    L = int(2.4 * SR); t = np.arange(L) / SR
    ir = rng.standard_normal((2, L)) * np.exp(-t * 2.6)
    ir[:, : int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    rev = np.stack([fftconvolve(wet[c], ir[c])[:N] for c in range(2)]) * 0.045
    Lg = int(0.28 * SR); tg = np.arange(Lg) / SR
    irg = rng.standard_normal((2, Lg)) * (tg < 0.24)  # gated 80s snare reverb
    gate = np.stack([fftconvolve(drums_gate[c], irg[c])[:N] for c in range(2)]) * 0.02
    mix = dry + rev + gate
    # gentle bus compression + soft clip
    mix = np.tanh(mix * 1.6) / 1.6
    tt = np.arange(N) / SR
    fade = np.clip(tt / 1.0, 0, 1) * np.clip((DUR - tt) / 2.5, 0, 1)
    mix *= fade
    mix /= np.max(np.abs(mix)) + 1e-9
    return mix * 0.89


def write(path, x):
    y = (np.clip(x, -1, 1) * 32767).astype('<i2').T.copy()
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())


if __name__ == '__main__':
    write(sys.argv[1], build())
