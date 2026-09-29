"""Scientific charts for the technical demo: explicit examples and recorded data.

No market observations are simulated implicitly. All illustrative inputs and
the single historical timing dataset are labelled in the slide captions.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parents[2] / "assets" / "plots_demo"
OUT.mkdir(parents=True, exist_ok=True)
INK, TEAL, GOLD, BLUE, GREY = "#0B1520", "#0369A1", "#B45309", "#6D28D9", "#7A8AA0"  # deck tokens: ink, cyan, amber, violet, muted
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 16, "axes.labelsize": 17,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#D9E2EC", "axes.labelcolor": "#44556A", "text.color": INK,
    "xtick.color": "#44556A", "ytick.color": "#44556A", "svg.fonttype": "none",
    "figure.facecolor": "#FFFFFF", "axes.facecolor": "#FFFFFF",
    "grid.color": "#E5EAF1",
})


def save(fig, name):
    fig.savefig(OUT / (name + ".svg"), bbox_inches="tight", pad_inches=.18)
    fig.savefig(OUT / (name + ".png"), bbox_inches="tight", pad_inches=.18, dpi=140)
    plt.close(fig)


def band():
    x = np.linspace(18, 22, 401)
    fig, ax = plt.subplots(figsize=(8.5, 5.3))
    mid = (x - 20) ** 2
    loss = lambda lo, hi: np.maximum(lo-x, 0)**2 + np.maximum(x-hi, 0)**2 + .05*mid
    ax.axvspan(19, 21, color=TEAL, alpha=.07)
    ax.plot(x, mid, color=GREY, lw=2.4, label="Mid")
    ax.plot(x, loss(19.5, 20.5), color=GOLD, lw=3, label="Haircut + anchor")
    ax.plot(x, loss(19, 21), color=TEAL, lw=3, label="Band + anchor")
    ax.set(xlabel="Model volatility (%)", ylabel="Loss (vol-point²)", ylim=(-.04, 4.25))
    ax.legend(frameon=False, loc="upper center")
    ax.grid(axis="y", alpha=.5)
    save(fig, "band")


def event_clock():
    days = np.linspace(5, 90, 350)
    event_day = 30
    extra = np.where(days >= event_day, 5, 0)
    fig, ax = plt.subplots(figsize=(8.5, 5.1))
    ax.plot(days, np.full_like(days, 20), color=TEAL, lw=3, label="Event-clock reading")
    ax.plot(days, 20*np.sqrt((days+extra)/days), color=GOLD, lw=3, label="Calendar reading")
    ax.axvline(event_day, color=GREY, ls=":", lw=1.5)
    ax.annotate("Expiry crosses event", xy=(30,21.6), xytext=(40,22.3),
                arrowprops={"arrowstyle":"->","color":GREY}, fontsize=15)
    ax.set(xlabel="Expiry (calendar days)", ylabel="Annualised volatility (%)", ylim=(19.4,23.2))
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", alpha=.5)
    save(fig, "clock")


def transport():
    k = np.linspace(-.20,.20,301)
    sigma = lambda z: .20-.30*z+.35*z*z
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for r,col in [(0,GREY),(1,TEAL),(2,GOLD)]:
        ax.plot(k,100*sigma(k+r*(-.02)),color=col,lw=3,label="R = "+str(r))
    ax.axvline(0,color="#b9c6cd",lw=1,ls=":")
    ax.set(xlabel="Current log-moneyness k",ylabel="Implied volatility (%)")
    ax.legend(frameon=False)
    ax.grid(axis="y",alpha=.5)
    save(fig,"transport")


def gate():
    x=np.linspace(0,1.6,301)
    fig,ax=plt.subplots(figsize=(8.5,5.1))
    ax.plot(x,np.maximum(1-x,0),lw=3.5,color=TEAL)
    ax.axvline(1,color=GREY,ls=":")
    ax.text(1.06,.16,"No operator row",fontsize=15)
    ax.set(xlabel="Observed support / required support",ylabel="Activation gap g",
           ylim=(-.04,1.06),yticks=[0,.25,.5,.75,1])
    ax.grid(axis="y",alpha=.5)
    save(fig,"gate")


def filtering():
    fig,ax=plt.subplots(figsize=(8.5,4.8))
    labels=["Prediction","Observation","Posterior"]
    vals=[20,20.4,20.32]
    std=[.30,.15,np.sqrt(1/(1/.3**2+1/.15**2))]
    for j,(label,v,s,col) in enumerate(zip(labels,vals,std,[GREY,GOLD,TEAL])):
        ax.errorbar(v,2-j,xerr=s,fmt="o",color=col,lw=4,capsize=10,ms=10)
        ax.text(v,2-j+.22,f"{v:.2f}%",ha="center",fontsize=17,color=col)
    ax.set(yticks=[2,1,0],yticklabels=labels,xlabel="ATM volatility (%)",
           xlim=(19.55,20.75),ylim=(-.5,2.6))
    ax.grid(axis="x",alpha=.5)
    save(fig,"filter")


def prior_shape():
    k=np.linspace(-.3,.3,301)
    old=20-30*k+60*k*k
    new=old+4
    anchored=old+4*np.exp(-(k/.065)**4)
    fig,ax=plt.subplots(figsize=(8.5,5.4))
    ax.axvspan(-.035,.035,color=TEAL,alpha=.08)
    ax.plot(k,old,color=GREY,lw=2,ls="--",label="Earlier smile")
    ax.plot(k,new,color=TEAL,lw=3,label="Same shape, +4 points")
    ax.plot(k,anchored,color=GOLD,lw=2.8,label="Earlier wings retained")
    ax.set(xlabel="Log-moneyness k",ylabel="Volatility (%)",ylim=(14,42))
    ax.legend(frameon=False,fontsize=13,loc="upper right")
    ax.grid(axis="y",alpha=.5)
    save(fig,"prior-shape")


def layered():
    fig,ax=plt.subplots(figsize=(8.5,5.3))
    t=np.arange(4)
    ax.plot(t,[10,13,13,14],"-o",color=GOLD,lw=2.6,label="Systematic prediction")
    ax.plot(t,[10,13,10,11],"-o",color=TEAL,lw=3,label="Target mark")
    ax.annotate("Target print = 10\nresidual = −3",xy=(2,10),xytext=(.35,8.7),
                arrowprops={"arrowstyle":"->","color":GREY},fontsize=15)
    ax.set(xticks=t,xticklabels=["Initial","Source update","Target print","Source update"],
           ylabel="Innovation (vol points)",ylim=(8,16))
    ax.tick_params(axis="x",labelsize=12)
    ax.legend(frameon=False,loc="upper left")
    ax.grid(axis="y",alpha=.5)
    save(fig,"layered")


def timings():
    fig,ax=plt.subplots(figsize=(8.5,5.5))
    names=["Prepared ladder","LQD-24 surface","LV · cold parameter start","LV · warm parameter start"]
    vals=[.354,.338,2.82,.89]
    ax.barh(np.arange(4),vals,color=[GREY,TEAL,BLUE,GOLD],height=.52)
    for i,v in enumerate(vals):
        ax.text(v+.06,i,f"{v:.3f} s" if v<1 else f"{v:.2f} s",va="center",fontsize=16)
    ax.set(yticks=np.arange(4),yticklabels=names,xlabel="Recorded wall time (seconds)",xlim=(0,3.5))
    ax.invert_yaxis()
    ax.tick_params(axis="y",labelsize=14)
    ax.grid(axis="x",alpha=.5)
    ax.set_axisbelow(True)
    save(fig,"timings")


if __name__ == "__main__":
    for draw in (band,event_clock,transport,gate,prior_shape,filtering,layered,timings):
        draw()
    print("Wrote 8 labelled scientific charts.")
