import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

out = Path('/mnt/data/mcsiv_figures')
out.mkdir(exist_ok=True)

def safe_logcosh(x):
    x = np.asarray(x)
    return np.where(np.abs(x) < 50.0, np.log(np.cosh(x)), np.abs(x) - np.log(2.0))

def Phi(u, kappa):
    return 4.0 / (kappa * kappa) * safe_logcosh(0.5 * kappa * u)

def Phi_p(u, kappa):
    return 2.0 / kappa * np.tanh(0.5 * kappa * u)

def Phi_pp(u, kappa):
    return 1.0 / np.cosh(0.5 * kappa * u) ** 2

def H(z, c, h, kappa):
    u = z - c
    return Phi(u - h, kappa) - 2.0 * Phi(u, kappa) + Phi(u + h, kappa)

def H_p(z, c, h, kappa):
    u = z - c
    return Phi_p(u - h, kappa) - 2.0 * Phi_p(u, kappa) + Phi_p(u + h, kappa)

def H_pp(z, c, h, kappa):
    u = z - c
    return Phi_pp(u - h, kappa) - 2.0 * Phi_pp(u, kappa) + Phi_pp(u + h, kappa)

def Hbar(z, c, h, kappa):
    height = H(np.asarray([c]), c, h, kappa)[0]
    return H(z, c, h, kappa) / height

def Hbar_p(z, c, h, kappa):
    height = H(np.asarray([c]), c, h, kappa)[0]
    return H_p(z, c, h, kappa) / height

def Hbar_pp(z, c, h, kappa):
    height = H(np.asarray([c]), c, h, kappa)[0]
    return H_pp(z, c, h, kappa) / height

def target_sigma(z):
    return (0.203
            - 0.0025 * z
            + 0.0035 * np.sqrt(1.0 + 0.6 * z * z)
            + 0.0105 * np.exp(-0.5 * ((z + 0.72) / 0.24) ** 2)
            + 0.0085 * np.exp(-0.5 * ((z - 0.70) / 0.25) ** 2)
            - 0.0120 * np.exp(-0.5 * (z / 0.30) ** 2))

def model_v(z, coeff):
    a, b, q, aL, aR, a0 = coeff
    return (a + b * z + q * Phi(z + 0.15, 1.15)
            + aL * Hbar(z, -0.72, 0.42, 5.0)
            + aR * Hbar(z, 0.70, 0.42, 5.0)
            + a0 * Hbar(z, 0.0, 0.55, 4.0))

def model_derivs(z, coeff):
    a, b, q, aL, aR, a0 = coeff
    v = a + b * z + q * Phi(z + 0.15, 1.15)
    vz = b + q * Phi_p(z + 0.15, 1.15)
    vzz = q * Phi_pp(z + 0.15, 1.15)
    for amp, c, h, kappa in [(aL, -0.72, 0.42, 5.0), (aR, 0.70, 0.42, 5.0), (a0, 0.0, 0.55, 4.0)]:
        v += amp * Hbar(z, c, h, kappa)
        vz += amp * Hbar_p(z, c, h, kappa)
        vzz += amp * Hbar_pp(z, c, h, kappa)
    return v, vz, vzz

z_fit = np.linspace(-3.0, 3.0, 61)
y = target_sigma(z_fit) ** 2
X = np.column_stack([
    np.ones_like(z_fit),
    z_fit,
    Phi(z_fit + 0.15, 1.15),
    Hbar(z_fit, -0.72, 0.42, 5.0),
    Hbar(z_fit, 0.70, 0.42, 5.0),
    Hbar(z_fit, 0.0, 0.55, 4.0),
])
coeff, *_ = np.linalg.lstsq(X, y, rcond=None)

z = np.linspace(-3.0, 3.0, 1201)
z_wide = np.linspace(-5.0, 5.0, 2001)
vol_fit = np.sqrt(model_v(z, coeff))
vol_tgt = target_sigma(z)
vol_fit_pts = np.sqrt(model_v(z_fit, coeff))
rmse = np.sqrt(np.mean((vol_fit_pts - target_sigma(z_fit)) ** 2))
maxerr = np.max(np.abs(vol_fit_pts - target_sigma(z_fit)))

# Figure 1: target and fit.
plt.figure(figsize=(7.0, 4.2))
plt.plot(z, 100.0 * vol_tgt, label='synthetic WW target')
plt.plot(z, 100.0 * vol_fit, '--', label='MC-SIV fit, R=3')
plt.scatter(z_fit, 100.0 * target_sigma(z_fit), s=12, label='quoted nodes')
plt.xlabel('normalized log-strike z')
plt.ylabel('implied volatility (%)')
plt.title('WW-shape smile fit with three zero-wing cores')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(out / 'ww_fit.pdf')
plt.savefig(out / 'ww_fit.png', dpi=220)
plt.close()

# Figure 2: component contributions in variance.
a, b, q, aL, aR, a0 = coeff
base = a + b * z + q * Phi(z + 0.15, 1.15)
plt.figure(figsize=(7.0, 4.2))
plt.plot(z, 10000.0 * (base - np.mean(base)), label='centered base variance')
plt.plot(z, 10000.0 * aL * Hbar(z, -0.72, 0.42, 5.0), label='left shoulder core')
plt.plot(z, 10000.0 * aR * Hbar(z, 0.70, 0.42, 5.0), label='right shoulder core')
plt.plot(z, 10000.0 * a0 * Hbar(z, 0.0, 0.55, 4.0), label='central notch core')
plt.xlabel('normalized log-strike z')
plt.ylabel('variance contribution (bp of variance)')
plt.title('Decomposition of the fitted WW geometry')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(out / 'ww_components.pdf')
plt.savefig(out / 'ww_components.png', dpi=220)
plt.close()

# Figure 3: butterfly diagnostic.
T = 7.0 / 365.0
sig_ref = 0.20
v, vz, vzz = model_derivs(z_wide, coeff)
w = T * v
wk = np.sqrt(T) / sig_ref * vz
wkk = vzz / (sig_ref * sig_ref)
k = z_wide * sig_ref * np.sqrt(T)
g = (1.0 - k * wk / (2.0 * w)) ** 2 - (wk * wk / 4.0) * (1.0 / w + 0.25) + 0.5 * wkk
plt.figure(figsize=(7.0, 4.2))
plt.plot(z_wide, g, label='g(k)')
plt.axhline(0.0, linestyle='--', linewidth=1.0, label='zero')
plt.xlabel('normalized log-strike z')
plt.ylabel('Durrleman/Gatheral g(k)')
plt.title('Butterfly-arbitrage diagnostic for the example fit')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(out / 'ww_g_diagnostic.pdf')
plt.savefig(out / 'ww_g_diagnostic.png', dpi=220)
plt.close()

with open(out / 'example_numbers.txt', 'w') as f:
    f.write('coefficients a,b,q,alphaL,alphaR,alpha0\n')
    f.write(','.join(f'{x:.12g}' for x in coeff) + '\n')
    f.write(f'rmse_vol={rmse:.12g}\n')
    f.write(f'max_abs_vol_error={maxerr:.12g}\n')
    f.write(f'min_v={v.min():.12g}\n')
    f.write(f'min_g={g.min():.12g}\n')
    f.write(f'z_at_min_g={z_wide[g.argmin()]:.12g}\n')
    f.write(f'right_wing_v_slope={b + 2*q/1.15:.12g}\n')
    f.write(f'left_wing_v_slope={b - 2*q/1.15:.12g}\n')
print(coeff)
print('rmse', rmse, 'maxerr', maxerr, 'min_g', g.min(), 'min_v', v.min())
