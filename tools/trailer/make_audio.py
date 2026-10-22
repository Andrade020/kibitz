"""Trilha sonora ORIGINAL do trailer, sintetizada em numpy (sem samples, sem direitos autorais).

Sincronizada com trailer.html pela mesma "dobra de tempo" (timeline.json): 100 BPM, 1 batida = 0,6 s, tom de Lá menor.
Impactos e sons de cena seguem a posição original do corte (T); ritmo, baixo e acordes são gerados em batidas reais (tempo constante).
Uso: python tools/trailer/make_audio.py   ->  build/trailer/audio.wav
"""
import json
import math
import wave
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve, lfilter

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "build" / "trailer"
TL = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
SR = 44100
SPB = 60 / TL["bpm"]
TOTAL = TL["total_beats"] * SPB
N = int((TOTAL + 2.5) * SR)
rng = np.random.default_rng(7)

# ---------------------------------------------------------------- dobra de tempo (igual à do trailer.html)
PTS, _o, _n = [(0.0, 0.0)], 0.0, 0.0
for _a, _b, _L in sorted(TL["warp"]):
    if _a > _o:
        _n += _a - _o
        _o = _a
        PTS.append((_o, _n))
    _n += _L
    _o = _b
    PTS.append((_o, _n))
if _o < TL["old_total_beats"]:
    _n += TL["old_total_beats"] - _o
    PTS.append((float(TL["old_total_beats"]), _n))


def W(bo):
    """batida original -> batida real."""
    for (o0, n0), (o1, n1) in zip(PTS, PTS[1:]):
        if bo <= o1:
            return n0 + (bo - o0) * (n1 - n0) / (o1 - o0)
    return PTS[-1][1] + (bo - PTS[-1][0])


def T(bo):
    """posição (s) de um cue em batidas originais."""
    return W(bo) * SPB


def TN(nb):
    """posição (s) em batidas reais."""
    return nb * SPB


def dur(a, b):
    """duração (s) entre duas batidas originais, já com a dobra."""
    return (W(b) - W(a)) * SPB


def bus():
    return np.zeros((N, 2))


def put(b, sig, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N or i < 0:
        return
    sig = sig[: N - i]
    g = np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)]) * gain * 1.414
    b[i:i + len(sig)] += sig[:, None] * g[None, :]


def tt(d):
    return np.arange(int(d * SR)) / SR


def lp(x, hz):
    a = np.exp(-2 * np.pi * hz / SR)
    return lfilter([1 - a], [1, -a], x)


def hp(x, hz):
    return x - lp(x, hz)


def noise(d):
    return rng.uniform(-1, 1, int(d * SR))


# ---------------------------------------------------------------- instrumentos
def kick(vol=1.0):
    t = tt(.5)
    f = 42 + 130 * np.exp(-t * 34)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t * 8.5) + .35 * np.sin(2 * ph) * np.exp(-t * 20)
    s[:90] += noise(90 / SR)[:90] * .5
    return s * vol


def snare(vol=1.0):
    t = tt(.32)
    return (hp(noise(.32), 1800) * np.exp(-t * 17) * .8 + np.sin(2 * np.pi * 185 * t) * np.exp(-t * 28) * .5) * vol


def clap(vol=1.0):
    t = tt(.28)
    env = np.exp(-t * 20) + .7 * np.exp(-np.clip(t - .012, 0, None) * 22) * (t > .012) + .5 * np.exp(-np.clip(t - .026, 0, None) * 22) * (t > .026)
    return hp(lp(noise(.28), 6500), 900) * env * .8 * vol


def hat(open_=False, vol=1.0):
    d = .35 if open_ else .09
    t = tt(d)
    return hp(noise(d), 7000) * np.exp(-t * (13 if open_ else 70)) * vol


def bass(freq, dur_, vol=1.0):
    t = tt(dur_)
    saw = 2 * ((freq * t) % 1) - 1
    s = np.sin(2 * np.pi * freq * t) * .8 + lp(saw, 420) * .5
    env = np.minimum(1, t / .01) * np.exp(-np.clip(t - dur_ * .55, 0, None) * 9)
    return s * env * vol


def pad(freqs, dur_, bright=1100, vol=1.0, atk=.6, rel=.9):
    t = tt(dur_)
    s = np.zeros_like(t)
    for f in freqs:
        for det in (-.0045, 0, .0045):
            s += 2 * ((f * (1 + det) * t) % 1) - 1
    s = lp(s / (3 * len(freqs)), bright)
    env = np.minimum(1, t / atk) * np.minimum(1, np.clip(dur_ - t, 0, None) / rel)
    return s * env * vol


def keys(freq, dur_=1.6, vol=1.0):
    t = tt(dur_)
    s = np.zeros_like(t)
    for k, a in ((1, 1), (2, .5), (3, .28), (4, .16), (5, .09), (6, .05)):
        s += a * np.sin(2 * np.pi * freq * k * t * (1 + .0004 * k * k)) * np.exp(-t * (1.6 + 1.5 * k))
    s *= np.minimum(1, t / .004)
    return s * vol * .55


def pluck(freq, dur_=.7, vol=1.0, decay=.995):
    n = int(dur_ * SR)
    D = max(2, int(SR / freq))
    x = np.zeros(n)
    x[:D] = rng.uniform(-1, 1, D)
    a = np.zeros(D + 2)
    a[0], a[D], a[D + 1] = 1, -decay / 2, -decay / 2
    return lfilter([1], a, x) * np.exp(-tt(dur_) * 1.2) * vol * .8


def bell(freq, dur_=1.8, vol=1.0):
    t = tt(dur_)
    s = sum(a * np.sin(2 * np.pi * freq * m * t) * np.exp(-t * d) for m, a, d in ((1, 1, 2.2), (2.76, .5, 3.4), (5.4, .25, 5.0), (8.9, .1, 8.0)))
    return s * vol * .45


def tick(vol=1.0):
    d = .016
    t = tt(d)
    f = rng.uniform(1500, 3000)
    return (hp(noise(d), 1200) * .6 + np.sin(2 * np.pi * f * t) * .5) * np.exp(-t * 340) * vol


def sweep(d, f0, f1, vol=1.0, shape=1.0):
    t = tt(d)
    f = f0 * (f1 / f0) ** (t / d)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (t / d) ** shape
    return (noise(d) * np.sin(ph) * .7 + np.sin(ph) * .35 + hp(noise(d), 4000) * .25 * env) * env * vol


def whoosh(d=.7, up=True, vol=1.0):
    t = tt(d)
    f = (300 * (9 ** (t / d))) if up else (2800 * (.12 ** (t / d)))
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 1.5
    return noise(d) * np.sin(ph) * env * vol * .9


def impact(vol=1.0, tail=2.4):
    t = tt(tail)
    f = 28 + 60 * np.exp(-t * 6)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.5)
    crash = hp(lp(noise(tail), 9000), 1500) * np.exp(-t * 2.2) * .35
    thud = lp(noise(tail), 300) * np.exp(-t * 7) * .8
    return (boom * 1.1 + crash + thud) * vol


def glitch(d=.35, vol=1.0):
    n = int(d * SR)
    out = np.zeros(n)
    i = 0
    while i < n:
        L = int(rng.uniform(.004, .028) * SR)
        seg = rng.uniform(-1, 1, L) if rng.random() < .6 else np.sin(2 * np.pi * rng.uniform(200, 3500) * np.arange(L) / SR)
        m = min(L, n - i)
        out[i:i + m] = seg[:m] * rng.uniform(.3, 1)
        i += L + int(rng.uniform(0, .02) * SR)
    return np.round(out * 8) / 8 * vol * .6


# ---------------------------------------------------------------- harmonia (em batidas REAIS: o acorde muda a cada 4)
PROG = ["Am", "F", "C", "G"]
PROG2 = ["C", "G", "Am", "F"]
CH = {"Am": [110, 130.8, 164.8], "F": [87.3, 110, 130.8], "C": [130.8, 164.8, 196], "G": [98, 123.5, 146.8]}
ROOT = {"Am": 55, "F": 43.65, "C": 65.4, "G": 49}
ARP = {"Am": [220, 261.6, 329.6, 440], "F": [174.6, 220, 261.6, 349.2], "C": [261.6, 329.6, 392, 523.3], "G": [196, 246.9, 293.7, 392]}
HIGH = {"Am": [440, 523.3, 659.3, 880], "F": [349.2, 440, 523.3, 698.5], "C": [523.3, 659.3, 784, 1047], "G": [392, 493.9, 587.3, 784]}


def chord_at(nb, prog=PROG):
    return prog[int(math.floor(nb / 4)) % 4]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    drums, bassb, pads, keysb, fx = bus(), bus(), bus(), bus(), bus()
    kicks = []

    def K(nb, v=1.0):
        put(drums, kick(v), TN(nb), 1.0, 0)
        kicks.append(TN(nb))

    def groove(nb0, nb1, snare_on=True, hats=16, kick_on=True, vol=1.0, bassline=True):
        step = .25 if hats == 16 else .5
        nb = math.ceil(nb0 / step) * step
        while nb < nb1 - 1e-6:
            ch, frac = chord_at(nb), nb % 4
            if kick_on and abs(nb - round(nb)) < 1e-6:
                K(nb, .95 * vol)
            if snare_on and (abs(frac - 1) < 1e-6 or abs(frac - 3) < 1e-6):
                put(drums, snare(.85 * vol), TN(nb), 1.0, 0)
                put(drums, clap(.5 * vol), TN(nb), 1.0, .1)
            acc = 1.0 if int(round(nb / step)) % 2 == 0 else .5
            put(drums, hat(abs((nb % 1) - .5) < 1e-6 and hats == 8 and rng.random() < .3, .35 * acc * vol), TN(nb), 1.0, rng.uniform(-.3, .3))
            if bassline and abs(nb * 2 - round(nb * 2)) < 1e-6:
                note = ROOT[ch] * (2 if int(round(nb * 2)) % 4 == 3 else 1)
                put(bassb, bass(note * 2, .27, .9 * vol), TN(nb), 1.0, 0)
            nb += step

    def pads_over(nb0, nb1, vol, bright, atk, rel, prog=PROG, extra_octave=False):
        for kb in range(int(math.floor(nb0 / 4)), int(math.ceil(nb1 / 4))):
            s, e = max(nb0, kb * 4), min(nb1, kb * 4 + 4) + .25
            ch = prog[kb % 4]
            put(pads, pad(CH[ch] + ([CH[ch][0] * 2] if extra_octave else []), (e - s) * SPB, bright, vol, atk=atk, rel=rel), TN(s), 1.0)

    # ------------------------------------------------ abertura sombria (0-8)
    put(pads, pad([55, 82.4, 110], T(9), 380, .55, atk=2.2, rel=1.0), 0, 1.0)
    put(fx, lp(noise(T(8)), 500) * np.minimum(1, tt(T(8)) / 3) * .12, 0, 1.0, 0)
    for spec in TL["typing"]:
        t0 = T(spec["b"]) + spec.get("offset", 0)
        for i in range(spec["n"]):
            put(fx, tick(.18 * spec["vol"]), t0 + i / spec["cps"], 1.0, rng.uniform(-.3, .3))
    put(fx, glitch(.7, .8), T(6.6), 1.0, 0)
    put(fx, np.sin(2 * np.pi * np.cumsum(220 * np.exp(-tt(1.1) * 2.2)) / SR) * np.exp(-tt(1.1) * 2.5) * .35, T(7.3), 1.0, 0)

    # ------------------------------------------------ lances absurdos e a pergunta (8-20)
    for b in (8, 11, 14):
        put(fx, impact(.62, 1.6), T(b), 1.0, 0)
        put(fx, glitch(.4, 1.0), T(b), 1.0, 0)
    for k, nb in enumerate(np.arange(math.ceil(W(8)), W(20), 1.0)):
        K(nb, min(.7, .42 + .03 * k))
    put(pads, pad([55, 82.4, 110, 130.8], dur(8, 20) + .5, 520, .5, atk=1.5, rel=1.2), T(8), 1.0)
    put(pads, pad([87.3, 130.8, 174.6], dur(14, 22), 600, .55, atk=1.2, rel=1.0), T(14), 1.0)
    put(fx, sweep(dur(16, 20), 250, 4200, .5, 1.6), T(16), 1.0, 0)
    for k, off in enumerate((2.0, 1.5, 1.0, .75, .5, .25)):
        put(drums, snare(.6 + .08 * k), TN(W(20) - off), 1.0, 0)

    # ------------------------------------------------ "era a visão" (20-24)
    put(fx, impact(1.1, 3.0), T(20), 1.0, 0)
    put(fx, whoosh(.9, False, .8), T(20), 1.0, 0)
    put(pads, pad([110, 130.8, 164.8, 220], dur(20, 24) + 1.2, 700, .55, atk=.4, rel=1.2), T(20), 1.0)
    put(fx, whoosh(.9, True, .9), T(21.35), 1.0, 0)
    for k, f in enumerate(HIGH["Am"] + [1318.5]):
        put(keysb, bell(f, 2.0, .35), T(21.5) + k * .06, 1.0, -.3 + .15 * k)
    put(fx, sweep(dur(22.6, 24), 400, 6000, .8, 2.2), T(22.6), 1.0, 0)

    # ------------------------------------------------ título + montagem (24-48)
    put(fx, impact(1.15, 3.2), T(24), 1.0, 0)
    for k, f in enumerate([440, 523.3, 659.3, 880, 1046.5, 880, 659.3, 523.3, 659.3, 880, 1318.5]):
        put(keysb, pluck(f, .9, .55), T(24.5) + k * .1, 1.0, -.4 + k * .08)
    groove(W(24), W(48), snare_on=True, hats=16, vol=1.0)
    pads_over(W(24), W(48), .75, 950, .12, .5)
    for nb in np.arange(math.ceil(W(32) * 4) / 4, W(48), .25):  # arpejo a partir da cena do jogo
        ch = chord_at(nb)
        put(keysb, pluck(ARP[ch][int(round(nb * 4)) % 4] * 2, .35, .42), TN(nb), 1.0, .2 * math.sin(nb))
    put(fx, whoosh(.7, True, .5), T(35.55), 1.0, 0)
    put(fx, whoosh(.7, True, .5), T(39.6), 1.0, 0)
    put(fx, whoosh(.6, True, .6), T(40) - .45, 1.0, 0)          # "sem lances ilegais"
    put(fx, impact(.9, 2.2), T(40), 1.0, 0)
    put(fx, glitch(.3, .9), T(40), 1.0, 0)
    put(fx, bell(1568, 2.4, .5), T(40.2), 1.0, .2)
    for i in range(39):                                           # legenda digitada
        put(fx, tick(.3), T(41.0) + i / 34, 1.0, rng.uniform(-.3, .3))
    for tk in (T(45.2), T(45.35)):                                # "clique" do cadeado
        put(fx, hp(noise(.03), 800) * np.exp(-tt(.03) * 180) * .9 + np.sin(2 * np.pi * 900 * tt(.03)) * np.exp(-tt(.03) * 220) * .4, tk, 1.0, 0)
    put(fx, sweep(dur(47, 48), 300, 5000, .45, 1.8), T(47.0), 1.0, 0)

    # ------------------------------------------------ a professora (48-64), emocional
    pads_over(W(48), W(64), .8, 820, .9, 1.2, extra_octave=True)
    for kb in range(int(math.floor(W(48) / 4)), int(math.ceil(W(64) / 4))):
        put(bassb, bass(ROOT[PROG[kb % 4]] * 2, 3.6 * SPB, .55), TN(max(W(48), kb * 4)), 1.0, 0)
    for k, nb in enumerate(np.arange(W(48), W(64) - .5, .5)):
        seq = HIGH[chord_at(nb)] + HIGH[chord_at(nb)][::-1][1:3]
        put(keysb, keys(seq[k % len(seq)], 1.8, .55), TN(nb), 1.0, -.25 + .1 * (k % 6))
    for b in (53.0, 56.3, 58.9):
        put(fx, whoosh(.6, True, .7), T(b) - .35, 1.0, 0)
        put(fx, bell(1318.5, 2.2, .6), T(b), 1.0, .2)
        put(fx, bell(1975.5, 2.2, .35), T(b) + .09, 1.0, -.2)
    put(fx, bell(880, 2.8, .6), T(50), 1.0, 0)
    put(pads, pad([110, 164.8, 220, 261.6], dur(50, 52), 900, .8, atk=.2, rel=.9), T(50), 1.0)
    put(fx, bell(1046.5, 2.6, .5), T(62.9), 1.0, 0)
    put(fx, sweep(dur(62.6, 64), 250, 6500, .7, 2.0), T(62.6), 1.0, 0)
    for k, off in enumerate((1.0, .75, .5, .375, .25, .125)):
        put(drums, snare(.55 + k * .08), TN(W(64) - off), 1.0, 0)

    # ------------------------------------------------ recursos (64-74): energia máxima
    groove(W(64), W(74), snare_on=True, hats=16, vol=1.1)
    pads_over(W(64), W(74), .8, 1300, .05, .4)
    for i in range(4):
        b = 64 + i * 2.5
        put(fx, whoosh(.35, True, .6), T(b) - .1, 1.0, rng.uniform(-.4, .4))
        put(bassb, bass(ROOT[chord_at(W(b))] * 2, .3, 1.0), T(b), 1.0, 0)
        put(fx, tick(.8), T(b), 1.0, 0)
    for k, f in enumerate(HIGH["Am"] * 2):
        put(keysb, pluck(f, .5, .35), T(64) + k * .15, 1.0, .1 * k - .4)

    # ------------------------------------------------ trio de golpes (74-80)
    for b, ch in ((74, "Am"), (76, "F"), (78, "G")):
        put(fx, impact(1.0, 2.0), T(b), 1.0, 0)
        put(pads, pad(CH[ch] + [CH[ch][0] * 2], dur(b, b + 2), 2200, 1.0, atk=.01, rel=.5), T(b), 1.0)
        put(fx, glitch(.25, .8), T(b), 1.0, 0)
    for nb in np.arange(math.ceil(W(74) * 2) / 2, W(79.65) - .1, .5):
        K(nb, .9)
    put(fx, sweep(dur(78.4, 79.65), 300, 7000, .9, 2.0), T(78.4), 1.0, 0)

    # ------------------------------------------------ instalação (80-88): leve e otimista
    pads_over(W(80), W(88), .7, 1000, .2, .7, prog=PROG2)
    for nb in np.arange(math.ceil(W(80) * 2) / 2, W(88), .5):
        ch = chord_at(nb, PROG2)
        put(keysb, pluck(ARP[ch][int(round(nb * 2)) % 4] * 2, .5, .45), TN(nb), 1.0, .3 * math.sin(nb))
    for nb in np.arange(math.ceil(W(80)), W(88), 1.0):
        K(nb, .55)
        put(drums, hat(False, .25), TN(nb + .5), 1.0, .2)
    for tm, f, d, v in ((81.4, 1318.5, 1.8, .45), (82.1, 1568, 1.8, .45), (82.8, 1975.5, 2.2, .5), (85.0, 2093, 1.6, .5)):
        put(fx, bell(f, d, v), T(tm), 1.0, 0)
    put(fx, tick(1.2), T(84.6), 1.0, 0)
    put(fx, sweep(dur(86, 88), 300, 7500, .9, 2.0), T(86), 1.0, 0)
    for k, off in enumerate((1.5, 1.0, .75, .5, .375, .25, .125)):
        put(drums, snare(.5 + k * .08), TN(W(88) - off), 1.0, 0)

    # ------------------------------------------------ final (88-104)
    put(fx, impact(1.25, 3.4), T(88), 1.0, 0)
    for k, f in enumerate([220, 329.6, 440, 523.3, 659.3, 987.8]):
        put(pads, pad([f], 15 * SPB, 1500, .5, atk=.05, rel=2.2), T(88) + k * .02, 1.0)
    for k, f in enumerate([880, 1046.5, 1318.5, 1760, 1318.5, 1046.5, 880, 659.3]):
        put(keysb, pluck(f, 1.0, .5), T(88.5) + k * .13, 1.0, -.4 + k * .1)
    groove(W(88), W(95), snare_on=True, hats=8, vol=.85)
    pads_over(W(88), W(100), .7, 1100, .1, .9)
    put(fx, bell(880, 4.0, .6), T(99.5), 1.0, 0)
    put(fx, bell(1318.5, 4.0, .45), T(99.55), 1.0, .2)
    put(fx, impact(.7, 3.5), T(99.5), 1.0, 0)

    # ------------------------------------------------ mixagem
    t_all = np.arange(N) / SR
    duck = np.ones(N)
    for k in kicks:
        i = int(k * SR)
        m = min(N - i, int(.4 * SR))
        if m > 0:
            duck[i:i + m] = np.minimum(duck[i:i + m], 1 - .55 * np.exp(-np.arange(m) / SR * 9))
    mix = drums * .95 + bassb * .85 * duck[:, None] + pads * .75 * duck[:, None] + keysb * .9 + fx * 1.0
    ir_t = np.arange(int(2.4 * SR)) / SR
    ir = [lp(rng.normal(0, 1, len(ir_t)) * np.exp(-ir_t * 2.3), 7000) * .018 for _ in range(2)]
    wet_src = keysb * .9 + fx * .8 + pads * .35
    mix = mix + np.stack([fftconvolve(wet_src[:, c], ir[c])[:N] for c in range(2)], axis=1) * .8
    c0 = T(79.65)                                   # silêncio dramático antes do trio, com 12 ms de fade
    mix *= np.where((t_all >= c0 - .012) & (t_all < T(80.0)), np.clip((c0 - t_all) / .012, 0, 1), 1.0)[:, None]
    mix = np.stack([mix[:, c] - .45 * lp(mix[:, c], 100) + .5 * hp(mix[:, c], 2500) for c in range(2)], axis=1)  # masterização
    mix *= np.clip((TOTAL - t_all) / 1.4, 0, 1)[:, None]
    mix *= np.clip(t_all / .05, 0, 1)[:, None]
    mix = np.stack([hp(mix[:, c], 28) for c in range(2)], axis=1)
    mix = np.tanh(mix / np.max(np.abs(mix)) * 1.35) / np.tanh(1.35) * .89
    pcm = (mix * 32767).astype(np.int16)
    out = OUT / "audio.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    rms = [float(np.sqrt(np.mean(mix[int(a * SR):int((a + 4) * SR)] ** 2)) + 1e-9) for a in range(0, int(TOTAL), 4)]
    print(f"audio: {out}  ({len(pcm) / SR:.1f}s, vídeo {TOTAL:.1f}s) | pico {np.max(np.abs(mix)):.2f}")
    print("energia por janela de 4s (dB):", [round(20 * math.log10(r), 1) for r in rms])


if __name__ == "__main__":
    main()
