"""Render the demo deck's equations to SVG (latex -> dvi -> dvisvgm, glyphs as
paths, fill=currentColor on the root so the deck's CSS colours them).
Every formula is set inside an unbreakable \\mbox (a bare $...$ in a preview
paragraph line-breaks at the text width); long ones are two-line `gathered`
displays so the deck can scale them without shrinking to nothing.
Output: Docs/deck/assets/eq_demo/<name>.svg"""
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(r"C:\Users\thiba\vol-fitter\Docs\deck\assets\eq_demo")
WORK = Path(__file__).parent / "build"
WORK.mkdir(exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

PRE = r"""\documentclass[preview,border=3pt]{standalone}
\usepackage{amsmath,amssymb}
\newcommand{\clip}{\operatorname{clip}}
\begin{document}
"""
POST = "\n\\end{document}\n"


def one(body: str) -> str:
    return r"\mbox{$\displaystyle " + body + "$}"


def two(a: str, b: str) -> str:
    return r"\mbox{$\displaystyle\begin{gathered}" + a + r"\\[4pt]" + b + r"\end{gathered}$}"


EQS = {
    # --- LQD
    "lqd_main": two(
        r"\ell(u)=\log q(u)=\underbrace{-\log u-\log(1-u)}_{\text{skeleton: exponential tails}}+\underbrace{(1-u)L+uR+\sum_{n=2}^{N}a_nP_n(1-2u)}_{g(u)\ \text{(tail scales + Legendre body)}}",
        r"f_X\big(Q(u)\big)=\frac{1}{q(u)}=u(1-u)\,e^{-g(u)}>0\quad\text{for every coefficient vector}"),
    "lqd_price": two(
        r"Q(z)=\mu+\int_0^{z}e^{\,g(\Lambda(t))}\,dt,\qquad \mu:\ \mathbb E\,e^{X}=1,\qquad z=\log\tfrac{u}{1-u}",
        r"C(k)=G(z_k)-e^{k}\,(1-u_k),\qquad G(z)=\int_z^{\infty}e^{Q(t)}\,\Lambda(t)\big(1-\Lambda(t)\big)\,dt"),
    "lqd_handles": one(r"\sigma_0=\sqrt{w_0/\tau},\quad s_0=\partial_k\sigma_{\rm imp}(0),\quad \kappa_0=\partial_{kk}\sigma_{\rm imp}(0)\qquad\text{from}\quad C'(0)=-(1-u_0),\ \ C''(0)=f_0-(1-u_0)"),
    "lqd_obj": one(r"\min_\theta\ \sum_i\omega_i\left(\frac{C^{\rm LQD}(k_i;\theta)-\mathrm{Black}(k_i,w_i)}{\partial_\sigma\mathrm{Black}(k_i,w_i)+\eta}\right)^{\!2}+\lambda\sum_{n\ge4}n^{2r}a_n^2,\qquad A_L=e^{g(0)},\ \ A_R=e^{g(1)}<1"),
    "lqd_jac": two(
        r"\frac{\partial C}{\partial\theta}=\frac{\partial A}{\partial\theta}\Big|_{z_k}\qquad\text{(the strike-root term cancels: } dA/dz=-e^{k}u_k(1-u_k)\text{)}",
        r"\partial_\theta Q'=Q'\,\phi,\qquad \phi=\big(1-u,\ u,\ P_2(1-2u),\dots,P_N(1-2u)\big)"),
    "lqd_guard": one(r"N_{\rm eff}=\max\!\Big(\min(N,6),\ \min\big(N,\lfloor n_q/2\rfloor-1\big)\Big)\qquad\text{(at most one parameter per two quotes)}"),
    "svi_jw": two(
        r"w(k)=a+b\Big(\rho(k-m)+\sqrt{(k-m)^2+\sigma^2}\Big)",
        r"v=\tfrac{w_0}{t},\quad \psi=\tfrac{b}{2\sqrt{w_0}}\Big(\rho-\tfrac{m}{\sqrt{m^2+\sigma^2}}\Big),\quad p=\tfrac{b(1-\rho)}{\sqrt{w_0}},\quad c=\tfrac{b(1+\rho)}{\sqrt{w_0}},\quad \tilde v=\tfrac{a+b\sigma\sqrt{1-\rho^2}}{t}"),
    "mcs": two(
        r"v_R(z)=V_0+S_0(z-z_0)+K_0\,\Phi_{\kappa}(z-z_0)+\sum_{r=1}^{R}\alpha_r\,\frac{\Phi_{\kappa_r}(u-h_r)-2\Phi_{\kappa_r}(u)+\Phi_{\kappa_r}(u+h_r)}{2\,\Phi_{\kappa_r}(h_r)}",
        r"\Phi_\kappa(u)=\tfrac{4}{\kappa^2}\log\cosh\tfrac{\kappa u}{2},\qquad u=z-c_r,\qquad w=t\,v_R"),
    # --- LV
    "dupire": two(
        r"\partial_T c=\tfrac12\,\nu(T,x)\,x^2\,\partial_{xx}c,\qquad c(0,x)=(1-x)^+,\qquad x=K/F",
        r"\nu_\theta(t,x)=\sum_\ell\theta_\ell\,\phi_\ell(t,x),\qquad \theta_\ell>0\ \text{vertex variances},\ \ \phi_\ell\ \text{tent functions on the triangulation}"),
    "bdf2": two(
        r"\big(I-\gamma\Delta t\,A^{n+1}\big)U^{n+1}=\alpha\,U^{n}-\beta\,U^{n-1}",
        r"\gamma=\tfrac{1+\omega}{1+2\omega},\quad \alpha=\tfrac{(1+\omega)^2}{1+2\omega},\quad \beta=\tfrac{\omega^2}{1+2\omega},\quad \omega=\tfrac{\Delta t_n}{\Delta t_{n-1}}\qquad(I-\gamma\Delta tA\ \text{an M-matrix for all }\gamma\in(0,1])"),
    "lv_sens": two(
        r"\big(I-\gamma\Delta t\,A^{n+1}\big)S^{n+1}=\alpha\,S^{n}-\beta\,S^{n-1}+\gamma\Delta t\;\phi\,\big(A\,U^{n+1}\big)\qquad(S=\partial U/\partial\theta)",
        r"\min_\theta\ \sum_i\omega_i\,\rho_i(\theta)^2+\lambda\|\Delta^2_x\theta\|^2+\rho\|\Delta^2_t\theta\|^2+\mu\|\Delta^3_k c\|^2"),
    # --- objective
    "haircut": two(
        r"\mathrm{lo}_i=\min(\mathrm{bid}_i+h,\ \mathrm{mid}_i),\qquad \mathrm{hi}_i=\max(\mathrm{mid}_i,\ \mathrm{ask}_i-h)",
        r"\mathrm{loss}_i=(m_i-\mathrm{hi}_i)_+^2+(\mathrm{lo}_i-m_i)_+^2+\theta_{\rm mid}\,(m_i-\mathrm{mid}_i)^2,\qquad \theta_{\rm mid}=0.05"),
    "weights": two(
        r"\omega_i\ \propto\ \max(\mathrm{raw}_i,\varepsilon)\cdot\min\!\Big(\frac{s_i}{\bar s},\,10\Big),\qquad s_i=\text{Voronoi cell width in }\log K",
        r"\mathrm{raw}_i\in\big\{1\ (\text{uniform}),\ \mathrm{TV}_i,\ \varphi(d_+)\ (\text{vega}),\ |\Delta_i|_{\rm OTM}\big\},\qquad \text{equal: } \omega_i=1\ \text{(no correction)}"),
    "operators": one(r"\mathrm{ATM}=\sigma(0),\qquad \mathrm{RR}_d=\sigma(k_{c,d})-\sigma(k_{p,d}),\qquad \mathrm{BF}_d=\tfrac12\big(\sigma(k_{c,d})+\sigma(k_{p,d})\big)-\sigma(0),\qquad d\in\{0.25,\ 0.10\}"),
    "deltastrike": one(r"k_{c,d}:\quad k=\tfrac12\,\sigma(k)^2\tau-\sigma(k)\sqrt{\tau}\;\Phi^{-1}(d)\qquad(\text{forward Black call delta; a put at }d\text{ is the call at }1-d)"),
    "varswap": two(
        r"w_{\rm vs}=2\Big[\int_0^{\infty}B(k,w)\,e^{-k}\,dk+\int_{-\infty}^{0}\big(B(k,w)+e^{k}-1\big)e^{-k}\,dk\Big],\qquad \sigma_{\rm vs}=\sqrt{w_{\rm vs}/t}",
        r"r_{\rm vs}=\sqrt{\text{weight}}\ \big(\sigma_{\rm vs}^{\rm model}-\sigma_{\rm vs}^{\rm quote}\big),\qquad \text{weight}=\tfrac{\rm pct}{100}\sum_i\omega_i\quad(\text{pct}=10\ \text{default};\ \text{hard pin}=10^4)"),
    "lee": two(
        r"\beta_R=\limsup_{k\to\infty}\frac{w(k)}{k}=\psi(p^*),\qquad \beta_L=\limsup_{k\to-\infty}\frac{w(k)}{|k|}=\psi(q^*),\qquad \psi(p)=2-4\big(\sqrt{p^2+p}-p\big)\in[0,2]",
        r"\text{LQD: }\ \beta_L=\psi(1/A_L),\quad \beta_R=\psi(1/A_R-1),\quad A_R<1;\qquad \text{SVI-JW: }\ \max(p,c)\sqrt{vt}\le\beta_{\max}=1.95"),
    "tails_alpha": two(
        r"\frac{dQ}{dz}=e^{g}\,\ell_-(u)^{-\alpha_-}\,\ell_+(u)^{-\alpha_+},\qquad \ell_-(u)=1-\log u,\quad \ell_+(u)=1-\log(1-u),\quad \alpha_\pm\in[0,\tfrac12]",
        r"\alpha>0:\quad w(k)\sim\tfrac12\Big(\tfrac{\lambda}{1-\alpha}\Big)^{\frac{1}{1-\alpha}}|k|^{\frac{1-2\alpha}{1-\alpha}},\qquad \alpha=0\ \text{linear wing (Lee slope }\psi),\quad \alpha=\tfrac12\ \text{Gaussian rate } w\to2\lambda^2"),
    # --- forwards / de-Am
    "parity": two(
        r"C(K)-P(K)=D\,(F-K)\quad\Longrightarrow\quad y_i=a+b\,K_i,\qquad D=-b,\quad F=a/D",
        r"\text{robust OLS: MAD trim } |r_i|>4\max(1.4826\,\mathrm{MAD},10^{-4}S),\ \le3\ \text{rounds};\quad \text{rate clamp } r\in[-5\%,30\%]"),
    "borrow": two(
        r"b_{i+1}=b_i+\frac{1}{t}\log\frac{F_{\rm theo}(b_i)}{F_{\rm parity}(b_i)},\qquad F_{\rm theo}=\big(S-\mathrm{PV}_{\rm div}\big)\,e^{(r-q-b)\,t}",
        r"\sigma_b=\frac{\mathrm{rms}}{t\sqrt{n}}\ \ (\text{noise floor}),\qquad \frac{\partial\sigma_{\rm ATM}}{\partial b}\approx125\sqrt{t}\ \text{vol bp per 100 bp of borrow}"),
    "deam": two(
        r"A_{\rm CRR}(\sigma^*)=A^{\rm mid}\ \Rightarrow\ E^{\rm mid}=P_{\rm Black}(\sigma^*),\qquad \widehat{\mathrm{EEP}}=\max\big(A^{\rm mid}-E^{\rm mid},0\big)",
        r"\{\mathrm{bid},\mathrm{mid},\mathrm{ask}\}_{\rm Eur}=\{\mathrm{bid},\mathrm{mid},\mathrm{ask}\}_{\rm Am}-\widehat{\mathrm{EEP}}\qquad(\text{OTM side only; the dollar spread is unchanged})"),
    # --- events
    "event_clock": one(r"\tau_{\rm days}(t)=365\,t+\sum_{t_e\le t}N_e,\qquad \sigma_{\rm work}=\sqrt{w/\tau},\qquad w=\sigma^2\tau\ \text{unchanged}\ \Rightarrow\ \text{prices unchanged}"),
    "event_detect": two(
        r"f_i=\frac{\Delta w_i}{d_i}\ \ (\text{forward variance per day}),\qquad r_i=\max(f_{i-1},f_{i+1})",
        r"N_i=d_i\Big(\frac{f_i}{r_i}-1\Big)\ \text{ if } f_i>1.03\,r_i\ \text{and}\ N_i\ge0.5\ \text{day, else no event};\quad\text{clip and repeat until no peak is left}"),
    # --- prior / Kalman
    "prior_gate": two(
        r"r_j=\sqrt{\lambda_j}\;\frac{O_j(\theta)-O_j(\text{prior})}{\text{scale}_j},\qquad \lambda_j=B\,\frac{\mathrm{gap}_j}{\sum_i\mathrm{gap}_i},\qquad B=\tfrac{\rm Pct}{100}\sum_q\omega_q",
        r"\mathrm{gap}_j=\Big(\clip\big(1-\tfrac{\pi_j^{\rm obs}}{\pi_j^{\rm req}},\,0,\,1\big)\Big)^{\gamma}\qquad\text{exactly }0\ \text{whenever}\ \pi_j^{\rm obs}\ge\pi_j^{\rm req}"),
    "kalman": two(
        r"x_t=(\sigma_0,s_0,\kappa_0),\qquad z_t=x_t+\epsilon_t\ \ (H=I),\qquad K=P^-\big(P^-+R\big)^{-1}",
        r"R=\rho\,G\,(J^{\!\top}J)^{+}G^{\!\top}\ \ \text{from the fit's own Jacobian},\qquad \rho=\clip\!\Big(\tfrac{\chi^2}{m-3},\,1,\,25\Big)"),
    "kalman_q": two(
        r"Q=\mathrm{diag}(q^2\Delta t)+\big(0.10\,|h|\,(0.03,\,0.05,\,0.5)\big)^2+Q_{\rm adapt},\qquad q=\big(30\ \text{bp},\ 0.02,\ 0.05\big)/\sqrt{\rm day}",
        r"\zeta=\frac{|\nu|}{\sqrt{P^-+R}}\ ;\qquad \zeta>3\ \Rightarrow\ P^-\leftarrow P^-\,(\zeta/3)^2\ \ (\text{capped }25)\quad\text{— a jump is admitted, not averaged away}"),
    # --- graph
    "graph_edge": two(
        r"z_i=x_i^{1}-x_i^{0}\in\mathbb R^3\ \ (\text{increment of the handles from the transported prior}),\qquad \text{lit: } d_s=\text{fit}_s-x^0_s",
        r"z_i=\beta_{ij}\,z_j+\epsilon_{ij},\qquad \epsilon_{ij}\sim\mathcal N\big(0,1/p_{ij}\big),\qquad \beta_{i\leftarrow j}^{\rm cal}=\big(T_j/T_i\big)^{\alpha_T},\ \ \alpha_T=1"),
    "graph_post": two(
        r"z_i\,\big|\,z_{\cdot}\sim\mathcal N\!\Big(\frac{\sum_j p_{ij}\beta_{ij}z_j}{q_i},\ \frac1{q_i}\Big),\qquad q_i=\sum_j p_{ij}",
        r"Q^{+}=Q_{\rm msg}+D_\kappa+H^{\!\top}R_dH,\qquad \hat z=(Q^{+})^{-1}H^{\!\top}R_d\,d,\qquad \Sigma^{+}=(Q^{+})^{-1},\qquad \pi_i^{+}=1/\Sigma^{+}_{ii}"),
    "graph_hops": one(r"\mathbb E[z_C]=\beta_2\beta_1\,\mathbb E[z_A],\qquad \mathrm{Var}(z_C)=(\beta_2\beta_1)^2\,\mathrm{Var}(z_A)+\frac{\beta_2^2}{p_1}+\frac{1}{p_2}"),
    "graph_smooth": two(
        r"Q_\Delta=D_\kappa+\eta\,L^{\beta}_{\rm dir}+\lambda\,(A_\rho+\nu I)^{-1},\qquad L^{\beta}_{\rm dir}=(I-K\circ\beta)^{\!\top}\Pi\,(I-K\circ\beta)",
        r"\kappa\ \text{stiffness to the baseline},\quad \eta\ \text{reach},\quad \lambda\ \text{unbalanced-OT tangent norm (shipped }\lambda=0)"),
    "graph_layered": two(
        r"z_{i,t}=\beta_{ij}\,z_{j,t}+u_{i,t}+\epsilon_{ij,t},\qquad u_{i,t+\Delta}=2^{-\Delta/H_i}\,u_{i,t}+\omega_{i,t}",
        r"\hat z_F=-\,Q_{H,FF}^{-1}\,Q_{H,FS}\,d_S\qquad(\text{harmonic completion of the free nodes after the directed pass})"),
}


def render(name: str, body: str) -> bool:
    tex = WORK / f"{name}.tex"
    tex.write_text(PRE + body + POST, encoding="utf-8")
    r = subprocess.run(["latex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
                       cwd=WORK, capture_output=True, text=True)
    if r.returncode != 0:
        log = (WORK / f"{name}.log").read_text(errors="ignore")
        m = re.search(r"^! .*$", log, re.M)
        print(f"FAIL {name}: {m.group(0) if m else 'latex error'}")
        return False
    svg = WORK / f"{name}.svg"
    r = subprocess.run(["dvisvgm", "-n", "-e", f"{name}.dvi", "-o", svg.name],
                       cwd=WORK, capture_output=True, text=True)
    if r.returncode != 0 or not svg.exists():
        print(f"FAIL {name}: dvisvgm {r.stderr[-200:]}")
        return False
    text = svg.read_text(encoding="utf-8")
    text = text.replace("<svg version=", "<svg fill='currentColor' version=", 1)
    (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
    return True


if __name__ == "__main__":
    names = sys.argv[1:] or list(EQS)
    ok = sum(render(n, EQS[n]) for n in names)
    print(f"{ok}/{len(names)} rendered -> {OUT}")
