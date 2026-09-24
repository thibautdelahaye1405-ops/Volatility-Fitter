"""Small numeric check: CRR depth accuracy + de-Am speed (scalar vs Numba batch)."""
import time, numpy as np
from volfit.core import american as am
from volfit.core import american_numba as an
from volfit.core.black import black_call

S, r, q, t = 100.0, 0.045, 0.012, 0.5
sig_true = 0.25
Ks = np.array([70, 80, 90, 95, 100, 105, 110, 120, 130], float)
is_call = Ks >= S

# 1) European leg of the CRR tree vs Black, in vol bp, at several depths
print("European CRR leg vs Black: max |sigma error| in vol bp")
for n in (48, 96, 128, 192, 501, 1001):
    errs = []
    for K, ic in zip(Ks, is_call):
        p = am.binomial_price(bool(ic), S, K, t, sig_true, r, q, n_steps=n, american=False)
        # invert with Black: bisection on sigma
        F = S*np.exp((r-q)*t); D = np.exp(-r*t); k = np.log(K/F)
        def bs(s):
            c = D*F*black_call(np.array([k]), np.array([s*s*t]))[0]
            return c if ic else c - D*F*(1-np.exp(k))
        lo, hi = 0.01, 2.0
        for _ in range(60):
            m = 0.5*(lo+hi)
            if bs(m) < p: lo = m
            else: hi = m
        errs.append(abs(0.5*(lo+hi) - sig_true)*1e4)
    print(f"  n={n:5d}: max {max(errs):7.3f} bp, median {np.median(errs):7.3f} bp")

# 2) De-Am round trip: price American at sig_true on a deep (2001-step) tree, invert at 192/24 & 501 scalar
print("\nDe-Am round trip (American price from a 2001-step tree, sigma_true=25%)")
px = np.array([am.binomial_price(bool(ic), S, K, t, sig_true, r, q, n_steps=2001, american=True) for K, ic in zip(Ks, is_call)])
an.warmup()
sig192 = am.deamericanize_batch(is_call, px, S, Ks, t, r, q)  # 192 / 24 numba
sig501 = np.array([am.deamericanize(bool(ic), p, S, K, t, r, q) for K, ic, p in zip(Ks, is_call, px)])
for K, a, b in zip(Ks, sig192, sig501):
    print(f"  K={K:5.0f}: 192/24 -> {(a-sig_true)*1e4:+7.2f} bp   501/Brent -> {(b-sig_true)*1e4:+7.2f} bp")

# 3) EEP at these strikes (put side)
eur = np.array([am.binomial_price(bool(ic), S, K, t, sig_true, r, q, n_steps=2001, american=False) for K, ic in zip(Ks, is_call)])
print("\nEEP (American - European), price units, 2001 steps:")
print("  " + "  ".join(f"K{K:.0f}:{e:.4f}" for K, e in zip(Ks, px-eur)))

# 4) Speed: one scalar Brent inversion (501), one batch of 300 quotes (192/24 numba), numpy fallback
K300 = np.linspace(60, 140, 300); ic300 = K300 >= S
sig_smile = 0.25 + 0.3*np.maximum(np.log(S/K300), 0)**2 + 0.05*np.maximum(np.log(K300/S), 0)
px300 = am.binomial_price_batch(ic300, S, K300, t, sig_smile, r, q, n_steps=501, american=True)
t0 = time.perf_counter(); am.deamericanize(False, float(px[2]), S, 90.0, t, r, q); t1 = time.perf_counter()
print(f"\nscalar Brent de-Am (501 steps): {(t1-t0)*1e3:.1f} ms")
for _ in range(2):
    t0 = time.perf_counter(); out = am.deamericanize_batch(ic300, px300, S, K300, t, r, q); t1 = time.perf_counter()
print(f"numba batch 300 quotes (192/24): {(t1-t0)*1e3:.1f} ms  -> {(t1-t0)*1e3/300:.3f} ms/quote; finite={np.isfinite(out).sum()}")
idx = np.flatnonzero(np.isfinite(out))
lo = max(am.SIGMA_LO, 1.5*abs(r-q)*np.sqrt(t/192))
t0 = time.perf_counter(); out2 = am._deam_bisect_numpy(ic300[idx], px300[idx], S, K300[idx], t, r, q, 192, 24, lo, None, None); t1 = time.perf_counter()
print(f"numpy lockstep fallback same batch: {(t1-t0)*1e3:.1f} ms; max|numba-numpy| = {np.nanmax(np.abs(out[idx]-out2)):.2e}")
print(f"tree steps: scalar {am.DEFAULT_STEPS}, batch {am.DEFAULT_BATCH_STEPS}, bisections {am.BATCH_BISECTIONS}; numba={an.NUMBA_AVAILABLE}")
