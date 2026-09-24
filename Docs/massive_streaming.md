# The Massive live book — plan, cap, health, merge

Why this note exists (the finding of 2026-09-23, verified live): Massive's
options **quotes** websocket allows about **1,000 contracts per connection**.
A subscribe frame that would cross the limit is refused **in full** — the
server answers `{"ev":"status","status":"error","message":"Subscription limit
reached for feed. Please remove some subscriptions and try again."}` — the
count is cumulative on the connection, and the plan allows one connection per
cluster. The app used to subscribe **every** contract of every selected
expiry in one frame (SPY 26 expiries = 10,560 contracts; NVDA 9 = 1,866),
dropped `status: "error"` frames silently, and reported "streaming" whenever
its thread was alive — so the light said *stream warming* for five days with
`ready: false` while a REST probe fed the spot. Throughput was never the
problem (parse + apply runs at 264k–473k events/s; a full SPY book read is
42 ms). The 2026-09-24 rework below is what runs now.

Code: `backend/volfit/data/massive_stream.py` (the provider mixin: plan,
cap, merge, honesty, health, lifecycle), `massive_ws.py` (the transport:
one connection, chunked and acknowledged frames, session-aware reconnects),
`massive_book.py` (the live book, the health counters, the frame parser).
Locks: `backend/tests/test_massive_stream.py`, `test_massive_ws*.py`,
`test_scheduler.py` (the roll + the REST memory), `test_datasource.py` (the
`stream` block).

## 1. The plan — `option_tickers(ticker, expiries)`

What the scheduler asks a provider to stream is its **plan**, not the ladder:

* the listed contracts of the selection (the day's contracts listing,
  `massive_listing.py`) **inside the shared per-expiry strike window**
  (`strike_window.strike_bounds(centre, expiry, today)` — the band the quote
  prep keeps, so nothing a fit would see is left out: a 2-day rung keeps a
  few percent around the money, a 1-year rung the wide band);
* around a **hysteresis-held centre**: the book's parity spot when the book
  serves, else the last REST spot (`_last_spot`, updated by every fetch),
  else **one** nearest-expiry snapshot page (`limit=250`), retried at most
  every 60 s on failure; re-centred only after a **> 5 %** move
  (`RECENTER_PCT`) so a spot wobbling across a strike boundary does not
  re-plan every tick. **No centre = empty plan** (never the whole ladder);
* ranked **nearest-the-money first**: |ln K/centre| / sqrt(T), stable (a
  call precedes its put).

`streaming_contracts()` reports the **requested** (pre-cap) set so the
scheduler's universe diff (`AppState.sync_streaming`) stays stable across
refusals and cap re-rankings.

## 2. The cap — `stream_cap`, `stream_connections`

Across **all** its tickers the provider subscribes at most
`stream_cap × stream_connections` contracts (env `VOLFIT_MASSIVE_WS_CAP`,
default **950**; `VOLFIT_MASSIVE_WS_CONNECTIONS`, default **1** — the current
plan allows one socket), nearest-the-money first, **cumulative** — two
tickers share the budget by rank, so each gets its belly. The remainder is
remembered as `_stream_dropped` ("N over cap" in the light). With several
connections the capped plan is split into groups of ≤ cap, one
`MassiveWebSocket` per group, all feeding **one** `LiveBook`; a re-plan keeps
a contract on the connection it already has and fills the new ones where
there is room (no boundary churn).

Measured offline on 2026-09-24 with the app's universe (window σ_ref = 1,
cap 950, one connection; the plan counted off the day's listing, the centres
off one snapshot page each — SPY 763.19, NVDA 222.95):

| ticker | expiries | listed | windowed plan (requested) | live (capped) | over cap |
|---|---|---|---|---|---|
| SPY | 25 | 10,218 | 10,122 | 874 | 9,248 |
| NVDA | 9 | 1,866 | 1,602 | 76 | 1,526 |
| total | | 12,084 | 11,724 | 950 | 10,774 |

Two readings of that table. The window at σ_ref = 1 is nearly inert on an
index ETF's listed ladder (the strike_window note says so): the cap does the
work, and the live set is the belly of every rung. And with ONE socket the
two names share the budget by rank — SPY's 25 rungs (dense short-dated
strikes) take 874 slots, NVDA's nearest-the-money 76 — so a second name's
belly is thin; a second connection (`VOLFIT_MASSIVE_WS_CONNECTIONS=2`, when
the plan allows it), a tighter per-name σ_ref, or a per-ticker floor in the
cap are the levers (the last two are riders). Everything over the cap is
served from the per-minute REST snapshot (§5), so no chain loses quotes —
only their cadence. Since the tiered-cadence layer (§7, the same day) the
budget is split by the allocation policy — the on-screen node first, a
floor per ticker, a fair share of the rest — so the 874 / 76 split above is
history: 475 / 475 without a focus.

## 2b. Vendor facts verified live (2026-09-24, in session)

* **Unsubscribe releases the count.** On one connection: subscribe 900 → 900
  acknowledged; unsubscribe 500; subscribe 500 NEW → all 900 held are
  acknowledged again; subscribe 200 more (1,100 held) → refused. So the
  ~1,000 limit applies to the contracts HELD at a time, not to the
  connection's lifetime — bucket rotation (subscribe, read, unsubscribe,
  next) is technically possible on Massive. It is still not used here: Massive
  sends no paint on subscribe (a contract shows nothing until it ticks), so a
  rotated bucket must dwell until its contracts trade, and the per-minute REST
  snapshot already gives every contract's last NBBO at once, faster and
  without churn.
* **A refused frame is answered with one status message per contract**
  (27 messages for a 200-contract frame), not one per frame: the first message
  is paired with the pending chunk and halved; the rest are logged at debug.
* **The acknowledgement text** is `subscribed to: Q.O:…`, one status message
  per contract, as the parser assumes; the app's 420-contract NVDA plan was
  acknowledged in full within a second of the auth, and the book served 18,842
  quotes in the first eight seconds of the 2026-09-24 session (≈ 550 msg/s).

## 3. The subscription — chunked and acknowledged

* Frames carry at most `SUBSCRIBE_BATCH` = **200** contracts (the initial
  subscribe after auth too). Every chunk is a **pending** record until the
  server acknowledges it — a `success` status per contract ("subscribed to:
  Q.O:…"), or a quote arriving for it (the implicit acknowledgement).
* `status: "error"` frames are **parsed**. "Subscription limit reached" is
  paired with the pending chunk it answers (FIFO — the server answers frames
  in order; when no acknowledgement has parsed yet on the connection, the
  last chunk sent): the farther half of that chunk is dropped into
  `refused` (the chunks are ranked, so the far end is the wing), the nearer
  half is re-sent — halving until the acknowledged count sits under the
  server's limit. Nothing is unsubscribed. `auth_failed` is recorded, the
  light goes red, and the loop waits the full backoff (no busy loop). Any
  other error is recorded and logged.
* Every connect / auth / acknowledgement count / error / drop / reconnect
  is logged on `volfit.massive_ws` (INFO; `serve.py` attaches a handler,
  since uvicorn configures only its own loggers).

## 4. Stream health — the model behind the light

`StreamStats` (thread-safe, shared by the connections): connected sockets
and the cluster URL, messages and quotes total, **messages per second over a
10-s sliding window**, last-message and last-quote ages (monotonic), the
last message's wall time, reconnects, the last error text and its age, the
auth-failed flag. The provider adds the subscription counts (subscribed /
acknowledged / refused / over cap / requested / cap), the session flag and
the per-ticker served flags: `provider.stream_stats()` → a plain dict, the
`stream` block of every source in `GET /datasources` (`StreamHealth` in
`routers/datasource.py`; null when not streaming). The frontend reads it in
the market pill's tooltip (`streamHealthLines`) and as one line under the
source in the Data-sources card (`streamHealthLine`: "812 acked · 340 msg/s ·
last tick 2 s").

The light (`feed_status` keeps the fetching wave's memoised probe; the
stream suffix and its colour are computed live on every call):

| reading | colour |
|---|---|
| `streaming 812 · 340 msg/s · last 2 s` | amber on the delayed cluster, **green** on the real-time cluster with quotes flowing |
| `stream warming · 950 subscribed, 0 acked` | amber |
| `stream refused: Subscription limit reached… · 1,866 requested / 950 cap` | **red** |
| `stream idle since 20:00 UTC · closed session` | amber (keyed on the last **message** age and the session clock) |
| `stream connecting · 950 subscribed` | amber |
| `stream dead · reconnecting (3)` | **red** |
| `stream auth failed: …` | **red** |

### Honesty per ticker

`is_streaming_ticker(ticker)` is true only when a connection runs **and** at
least one of the ticker's planned contracts is acknowledged **and** at least
one of them is booked. `AppState.is_streaming(ticker)` asks that question,
so an unserved ticker stays on the **request path** — `autoUpdate` keeps
working, the per-node SSE says *not streaming* — while the provider-level
`is_streaming()` stays "the stream is wanted" for start / stop. A connection
whose thread died while wanted is **revived in place** (the book and the live
set kept), counted as a reconnect and logged — never a silent restart with an
empty book.

## 5. The merge — book + REST for the remainder

`_chain_from_book` emits **every** listed contract of the selection: booked
ones with their tick (stamped at the provider tick time), the rest — over
cap, beyond the window, not yet acknowledged — from the ticker's **last REST
snapshot** with that snapshot's own stamps, else unquoted. The chain's stamp
is the newest booked tick; the spot is the parity forward of the **booked**
quotes (the belly), so a stale wing never moves it. The REST memory is seeded
by every live two-sided REST `fetch_chain` (the first frame after a start
falls through to REST) and refreshed by `refresh_stream_rest(ticker,
expiries)` — the scheduler's streaming branch calls it every tick, the
provider throttles it to **one windowed snapshot per ticker per minute**
(`STREAM_REST_SECONDS` = 60) on a background worker, using the fetching
wave's paging (nearest expiry unwindowed, the rest windowed).

## 6. Day roll and the silence rule

* **Roll**: when the exchange day moves under a running server the scheduler
  calls `AppState.refresh_provider_contracts()` — every provider with
  `refresh_contracts()` drops its listing, ladder, contract keys and stream
  plans — and the next `sync_streaming` re-plans: expired rungs are
  unsubscribed, the new one subscribed. Not on the first tick (the day's
  listing on disk is fresh).
* **Silence**: outside the US options session (09:30–16:15 ET on a trading
  day, `expiry_time.session_open_now`; injectable clock) a connected socket
  is **kept** — silence is expected, there is no rotation and no reconnect
  churn (locked: a closed-session socket with no frames reconnects 0 times
  over a simulated hour). Inside the session a **first** connection with no
  quote for `quote_grace` (6 s) rotates to the next candidate cluster
  (real-time → delayed), and a serving connection with no message at all for
  `SILENCE_RECONNECT_S` = 30 s reconnects to the same cluster. A session
  that served reconnects after 1 s; a closed / errored one with a capped
  backoff (1 → 30 s).

## 7. Focus, fair share and cadence (2026-09-24)

The cap of §2 was shared by **global** nearest-the-money rank: on the app's
universe SPY's 25 dense rungs took 874 of the 950 slots and NVDA got 76. The
desk wants the node **on screen** ticking at full NBBO rate, every ticker a
fair share of the remainder, and the unviewed rest at a slower but honest
cadence. Three pieces:

**The focus** (`backend/volfit/api/stream_focus.py`). The per-node tick-stream
SSE (`GET /smiles/{t}/{e}/table/stream`, opened by the Quote Table / Smile
Chart for the viewed node) is the app's signal of what the desk is looking
at: `table_events` registers its `(TICKER, expiry)` on entry and drops it on
exit (the generator's `finally` — a disconnect, an error, a close),
reference-counted (two tabs on one node = one focus; the focus ends when the
last closes). `AppState.stream_focus()` is the set; `sync_streaming` hands
each provider its tickers' nodes every scheduler tick through
`set_stream_focus(nodes)`, which answers whether they **changed** — that,
and only that, makes an unchanged universe re-plan (`update_streaming` in
place: a diff, no restart; a quiet tick never re-plans).

**The allocation policy** (`backend/volfit/data/stream_allocation.py`, pure,
shared with the Bloomberg cap — `bloomberg_plan.py`). Given each ticker's
ranked plan, the focus, the budget (cap × connections) and the per-ticker
floor (`VOLFIT_MASSIVE_WS_FLOOR`, 60):

1. **focus** — every planned contract of the focus nodes, nearest-the-money
   first, round-robin across focus tickers; the floors of the tickers
   *without* a focus are reserved first, so an on-screen SPY rung cannot
   starve NVDA;
2. **floors** — one contract at a time to the tickers still under the floor;
3. **fair share** — one contract at a time to the ticker with the fewest
   non-focus live contracts (water-filling: an equal split of the remainder,
   the focus not charged against it) until the budget is spent.

Deterministic (tickers in name order) and **stable**: each ticker's live set
is a rank prefix of its plan (plus its focus rung), so a re-plan on unchanged
inputs returns the same contracts and a change moves only a ticker's far end
— the provider diffs the sets, and a spot wobble inside the window's
hysteresis moves nothing. The live list is in priority order (focus, floors,
rounds): the transport subscribes in that order, so a refused chunk (§3)
trims the least valuable half.

Recomputed offline on 2026-09-24 (the day's listing cache, centres SPY
763.19 / NVDA 222.95, cap 950, one connection; the app's universe = SPY's
nearest 25 expiries, NVDA's nearest 9):

| | planned (windowed) | live, no focus | live, NVDA Oct-16 on screen |
|---|---|---|---|
| SPY (25 rungs) | 9,022 | 475 | 390 |
| NVDA (9 rungs) | 1,014 | 475 | 560 (its Oct-16 rung: 170 of 170) |
| NVDA Oct-16 rung | 170 | 69 live → tier `rest` | 170 live → tier `live` |

(The whole ladders on disk — SPY 28 / NVDA 20 expiries, 10,544 / 3,026
planned — split the same way: 475 / 475, then 390 / 560.) Versus §2's
874 / 76.

**The cadence.** The focus rungs and the fair-share bellies tick live;
everything else comes from the REST memory (§5) every
`VOLFIT_MASSIVE_REST_SECONDS` (60, floored at 15 — the provider's
`rest_seconds`). The per-node SSE says which: every frame carries `tier` —
`live` (the node's whole planned rung is on the socket), `rest` (its belly
ticks, its wings are the memory's; `restSeconds` names the cadence) or
`none` — and a tier change alone pushes one status frame, so the Quote Table
/ Smile Chart badge reads **LIVE** (green, pulsing) or **1-min REST** (blue,
steady) honestly. `stream_stats()` / the `/datasources` `stream` block carry
`allocation` (per ticker `requested` / `live` / `focus`), `focus`, `floor`
and `restSeconds`; the market pill's tooltip shows the shares.

Locks: `tests/test_stream_allocation.py` (the policy on SPY / NVDA-shaped
plans), `test_massive_stream.py` (focus → whole rung live, re-plan only on a
change, tier, the knobs), `test_table_stream.py` (the SSE's focus for its
lifetime, tier frames), `test_bloomberg_stream.py` (per-security intervals,
the focus resubscribe).

## Operator notes

* Knobs: `VOLFIT_MASSIVE_WS_CAP` (950), `VOLFIT_MASSIVE_WS_CONNECTIONS` (1),
  `VOLFIT_MASSIVE_WS_URL` (the cluster override; a delayed-tier key points
  straight at `wss://delayed.polygon.io/options`), `VOLFIT_MASSIVE_WS_FLOOR`
  (the per-ticker floor of §7, 60), `VOLFIT_MASSIVE_REST_SECONDS` (the REST
  cadence behind the book, 60, floor 15).
* Verify live after a restart: the `volfit.massive_ws` log lines
  (connect → authenticated → acknowledged N → the first quote), the
  `/datasources` `stream` block (`acknowledged` climbing, `refused` 0,
  `rate` > 0 in session), the market pill's tooltip, and the per-node SSE's
  `ready: true` once the ticker's belly ticks.
* A red "stream refused" reading means the server's limit is below the cap:
  lower `VOLFIT_MASSIVE_WS_CAP`; the halving already keeps what fits.

## Recorder — the socket in its own process (2026-09-24)

Why: the key allows **one** quotes socket. Held by the API process it dies
with every restart (the book re-warms, the day's ticks are gone), a second
`/options` connection is refused and disturbs the first, and nothing of the
day is replayable. The **tick recorder** is a separate process that owns the
socket; the API reads the book it writes and opens **no** socket of its own.

Code: `backend/volfit/data/tick_recorder.py` (the loop), `tick_recorder_cli.py`
(`record` / `replay` / `status` / `stop`), `tick_store.py` (the daily SQLite
file), `massive_recorded.py` (the API-side reader + the provider overrides);
`record.ps1` at the repo root. Locks: `backend/tests/test_tick_store.py`,
`test_tick_recorder.py`, `test_massive_recorded.py`.

### What the recorder does

* Builds the **same** `MassiveProvider` serve.py builds (key, cluster
  override, cap / connections, NBBO history, the on-disk listing cache),
  resolves the expiry rule per ticker (`all` | `monthly` = third Fridays |
  `weekly` = Fridays | a CSV of ISO dates), **plans and streams through the
  provider's own mixin** (§1–3: the window, the cap, the chunked acknowledged
  frames — nothing re-implemented).
* Every `--interval` (1 s): folds the `LiveBook` into the day's tick store —
  `ticks_<ET day>.sqlite` under `backend/data/ticks/` — **changed ticks
  only** (`ticks` is append-only, one row per change of (bid, ask, ts);
  `latest` is the book as it stands), writes the **heartbeat** and the
  provider's `stream_stats()` (plus `ackedByTicker`, the per-ticker
  acknowledged counts) into `meta`, with the pid, the start time and the
  plan (tickers, expiries, requested / subscribed / over-cap / refused).
* Every `--frame-minutes` (1): refreshes the REST memory (the provider's own
  per-minute throttle, `--no-rest` turns it off) and saves each ticker's
  chain — the provider's **book read**, `live_chain` — into the app's
  VolStore (`--store`, `VOLFIT_DB`) as an as-of reconstruction: `source =
  "massive"`, `series_id = "_asof"`, the request ladder recorded, stamped at
  the book's **newest tick time floored to the frame minute**. Unquoted
  rows are not saved (the request covers them). The store-first as-of
  (`volfit.api.asof_cache`) serves that instant from the row once the
  session is final, and the Series lens's import lists it — no REST harvest.
  A frame is skipped when no tick arrived since the last one.
* Day roll: a new daily file, the listing re-pulled, the live set re-planned
  (`update_streaming`). A clean stop on Ctrl-C or on the `stop` meta key
  (`record.ps1 -Stop` posts it and waits; the pid is the fallback): the last
  fold, the stream down, `stoppedAt` in `meta`.

### What the API does with `VOLFIT_MASSIVE_BOOK`

`VOLFIT_MASSIVE_BOOK = recorder:<file or directory>` (a directory = today's
daily file, re-resolved on the day roll) makes serve.py's Massive provider
attach a `RecordedBook` — the `LiveBook` read interface (`quote`, `any_of`,
`newest_ts`, `size`) over the store's `latest` table, cached for **one second
per read burst** (the per-node SSE polls at 1 Hz; a chain read touches
~10,000 contracts and must not run 10,000 queries):

* `start_streaming` computes the plan (the merge needs the requested set and
  the over-cap count) and attaches the reader — **never a
  `MassiveWebSocket`** (locked); `stop_streaming` detaches;
* `is_streaming()` = the reader is alive (heartbeat younger than 10 s);
  `is_streaming_ticker(t)` = alive **and** the recorder's stats say one of
  the ticker's planned contracts is acknowledged on *its* socket **and** a
  quote of the ticker is in `latest`; `stream_stats()` = the recorder's
  stats with `source: "recorder"`, `heartbeatAge`, the API's own per-ticker
  honesty; the REST memory keeps refreshing behind the recorded belly;
* the light's suffix reads `recorded book · 812 acked · last tick 2 s ·
  recorder alive` (amber; green when the recorder's own reading is green) or
  **`recorder stale (42 s)`** (red — no ticker is served then, the request
  path takes over).

The merge (§5) and the per-node SSE run unchanged over the recorded book.
Rider: `stream_tier` reads "rest" for every node in recorded mode (the
recorder's live set is not yet handed over through the store).

### Operate

```
.\record.ps1 -Tickers SPY,NVDA -Expiries all          # detached; logs backend\data\recorder.*.log
.\record.ps1 -Status                                   # pid, heartbeat age, acked, frames, plan
.\record.ps1 -Stop                                     # clean stop (the pid as fallback)
$env:VOLFIT_MASSIVE_BOOK = 'recorder:C:\...\backend\data\ticks'   # in restart.local.ps1
.\restart.ps1 -Massive                                  # the app reads the recorded book
cd backend ; ..\.venv\Scripts\python -m volfit.data.tick_recorder replay `
    --db data\ticks\ticks_2026-09-24.sqlite --ticker SPY --at 2026-09-24T15:45:00 --store data\volfit.sqlite
```

Verify: `recorder.err.log` shows the stream's connect → acknowledged lines
and `SPY: frame 2026-09-24T15:45:00 saved (#…, N quotes, spot …)` once a
minute in session; `-Status` shows a heartbeat a second old and `acked` > 0;
the app's `/datasources` `stream` block carries `source: "recorder"` and the
light says *recorded book … recorder alive*; stop the recorder and the light
turns red *recorder stale (N s)* within ten seconds.
