// Settings documentation — MarketSettings (HELP CENTER ARC, H1): the
// per-ticker carry inputs behind the theoretical forward and the de-Am tree,
// edited in the Forwards lens (components/ForwardPanel.tsx "Carry r / div q"
// row + components/DividendEditor.tsx "Dividend model" card). Prose only:
// type / default / enum come from settingsSchema.json.
//
// Cache discipline: AppState.set_market_settings bumps that ticker's forwards
// version and clears its joint-carry solve when the settings differ — so the
// name's fits recompute through their resolved forwards while every other
// ticker stays warm ("per-ticker-version").
//
// Sources: volfit/api/schemas_market.py (MarketSettings, DividendSpec),
// volfit/data/dividends.py (the four modes' formulas — NB "mixed" switches
// cash → PROPORTIONAL at switchYears, not cash → continuous as the handoff
// table §3 says), Docs/handoff/notes/06 §6 (dividends).
import type { SettingDoc } from "../types";

export const MARKET_DOCS: SettingDoc[] = [
  {
    key: "rate",
    model: "market",
    section: "market",
    label: "Carry r (rate)",
    unit: "per year (decimal)",
    summary: "Set the ticker's flat continuously compounded interest rate behind its theoretical forwards and de-Americanization.",
    details:
      "The theoretical forward grows spot at r and takes the dividend model off; the Forwards lens shows it in the Theo column beside the parity read. It is used by every expiry whose forward policy is `theoretical`, as the physical carry of the escrowed-dividend de-Am tree, and as the discount fallback e^(−rt) when parity yields none. A desk-owned input (`rateSource` = desk), never inferred — the option-implied borrow is read separately from the parity-vs-theo gap.\n\n" +
      "Default 0 keeps zero-carry fixtures exact. Changing it bumps this ticker's forwards version, so that name's fits recompute through their resolved forwards and its joint-carry solve clears; every other ticker stays warm.",
    example:
      "SPY at 0.045: the Theo forward of a 1Y expiry reads about spot × 1.046 less dividends, and the implied-borrow column shifts by the gap between this rate and the parity read.",
    cacheEffect: "per-ticker-version",
    surfaced: true,
    related: ["dividendMode", "dividendYield", "jointCarry", "help:guides:forwards"],
    docs: ["06_forwards_dividends_inference"],
  },
  {
    key: "dividendMode",
    model: "market",
    section: "market",
    label: "Dividend model",
    summary: "Choose how dividends enter the ticker's carry — continuous yield, discrete cash, discrete proportional, or mixed.",
    details:
      "`continuous` (Cont, the default): F = S·e^((r−q)t) with `dividendYield` — the cheap proxy. `discrete_absolute` (Cash): escrowed cash per ex-date, F = (S − PV of dividends)·e^(rt); cash does not scale with the stock, so the forward outruns spot in a rally (elasticity above 1). `discrete_proportional` (Prop): fractions of spot, F = S·e^(rt)·Π(1 − dᵢ); elasticity exactly 1. `mixed`: cash for ex-dates inside `switchYears`, proportional beyond — the realistic single-name shape, since near dividends are declared in currency and far ones are better known as a payout ratio.\n\n" +
      "At a fixed spot the discrete modes give nearly the same forward; they part when spot moves, which the sticky-strike transport inherits — so this is a risk choice, not a cosmetic one. The same model drives the de-Am escrow tree. Per-ticker version bump.",
    example:
      "AAPL with a 0.26 quarterly schedule: switch Cont (q 0.5%) to Cash and the implied-carry term structure turns from a flat line into a sawtooth with one tooth per ex-date, while the 1Y forward moves by only a few cents.",
    cacheEffect: "per-ticker-version",
    surfaced: true,
    related: ["dividends", "dividendYield", "switchYears", "rate", "help:guides:forwards"],
    docs: ["06_forwards_dividends_inference"],
  },
  {
    key: "dividendYield",
    model: "market",
    section: "market",
    label: "div q (continuous yield)",
    unit: "per year (decimal)",
    summary: "Set the flat continuous dividend yield q used by the continuous dividend model.",
    details:
      "F = S·e^((r−q)t): q shaves the carry uniformly across maturities. The panel's footnote 'r always · q used in continuous mode' is the rule — under the discrete and mixed modes the schedule replaces q entirely, so a non-zero q is ignored there.\n\n" +
      "Default 0 keeps zero-carry fixtures exact. The equivalent yield of a discrete schedule (2.59% for the reference cash schedule at 1Y) is a diagnostic the forward machinery computes, not this setting. Per-ticker version bump.",
    example:
      "SPY q 0.013 with r 0.045: the Theo 1Y forward sits about 3.2% above spot instead of 4.6%, and the parity-vs-theo borrow reads shrink toward zero on an index paying about 1.3%.",
    activation: "Read only while dividendMode is continuous",
    cacheEffect: "per-ticker-version",
    surfaced: true,
    related: ["dividendMode", "rate", "help:guides:forwards"],
    docs: ["06_forwards_dividends_inference"],
  },
  {
    key: "dividends",
    model: "market",
    section: "market",
    label: "Dividend schedule (ex-date, amount)",
    summary: "Enter the ticker's discrete dividends as ex-date and amount rows.",
    details:
      "Each row is one `DividendSpec`: an ISO ex-date and an amount ≥ 0. Under Cash and the near leg of Mixed the amount is currency per share; under Prop it is a fraction of spot in [0, 1); under the far leg of Mixed a currency amount re-read as a fraction of the prevailing spot. Only rows with an ex-date inside (0, t] enter an expiry's forward, so a schedule running past the last expiry is harmless.\n\n" +
      "The editor validates ex-dates and ranges ahead of the backend's 422. The same schedule feeds the de-Am escrow tree, so a wrong cash amount shows up as a put/call de-Am vol split at the money. Per-ticker version bump.",
    example:
      "MSFT with four rows of 0.83 on the next four ex-dates: the Theo forward steps down by about 0.83 (discounted) at each ex-date, and the implied-carry curve shows one tooth per row.",
    activation: "Read only while dividendMode is discrete_absolute, discrete_proportional or mixed",
    cacheEffect: "per-ticker-version",
    surfaced: true,
    related: ["dividendMode", "switchYears", "help:guides:forwards"],
    docs: ["06_forwards_dividends_inference"],
  },
  {
    key: "switchYears",
    model: "market",
    section: "market",
    label: "Switch (yrs)",
    unit: "years",
    summary: "Set the horizon at which the mixed dividend model switches from escrowed cash to proportional.",
    details:
      "Ex-dates with τ ≤ `switchYears` are priced as escrowed cash — declared amounts, exact timing; beyond it each amount is re-read as a fraction of spot (amount / S) and applied proportionally, because far dividends are known as a payout ratio rather than in currency. Default 1 year: the horizon over which a company's declared dividends are reliable.\n\n" +
      "Shortening it makes long-dated forwards elasticity-1 sooner and truncates the de-Am cash schedule at the same horizon. Per-ticker version bump.",
    example:
      "Mixed with 0.5: a dividend 9 months out that was escrowed at 0.83 becomes a 0.2% proportional haircut, the 1Y forward changes by a few cents and its spot elasticity drops from about 1.01 to 1.",
    activation: "Read only while dividendMode is mixed",
    cacheEffect: "per-ticker-version",
    surfaced: true,
    related: ["dividendMode", "dividends", "help:guides:forwards"],
    docs: ["06_forwards_dividends_inference"],
  },
];
