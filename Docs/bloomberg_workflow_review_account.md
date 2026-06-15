# Bloomberg Help-Desk Account — `WORKFLOW_REVIEW_NEEDED` data gating

A complete, copy-pasteable technical account for the Bloomberg Help Desk.

**Headline:** the API connects to the Terminal successfully, but every
market-data request is refused server-side with a `WORKFLOW_REVIEW_NEEDED`
entitlement gate. This is an **account / entitlement** question, not a
connectivity or software one — no client-side change can release it.

*Captured 2026-06-15 against a local Terminal on this machine.*

---

## 1. Environment

- **Access path:** Bloomberg Desktop API (DAPI) to a locally running Terminal,
  `localhost:8194`.
- **Client libraries:** `blpapi` **3.26.5.1** (the official Python SDK), driven
  through the `xbbg` **1.3.0** convenience wrapper (a pyo3/Rust engine over
  blpapi). The wrapper is irrelevant to the gating — the requests it issues are
  standard blpapi `//blp/refdata` requests.
- **OS:** Windows 11.

## 2. What we do, and how we request data

We open a single blpapi `Session` to the Terminal and issue standard requests
against the **`//blp/refdata`** service (plus `//blp/instruments` for symbol
search):

| Purpose | blpapi operation | Security / fields |
|---|---|---|
| Spot price probe | `ReferenceDataRequest` (`bdp`) | `SPY US Equity`, field `PX_LAST` |
| Option chain enumeration | `ReferenceDataRequest` bulk (`bds`) | `SPY US Equity`, field `OPT_CHAIN` |
| Per-contract NBBO | `ReferenceDataRequest` (`bdp`) | option securities, fields `BID, ASK, LAST_PRICE, VOLUME, OPEN_INT, OPT_EXER_TYP` |
| Dividend schedule | `ReferenceDataRequest` bulk (`bds`) | `DVD_HIST_ALL` |
| Historical EOD chains | `HistoricalDataRequest` (`bdh`) | `PX_BID, PX_ASK, PX_LAST, PX_VOLUME, OPEN_INT` |
| Symbol search | `//blp/instruments` `instrumentListRequest` | free-text query |

Request volumes are modest (a handful of underlyings; option chains are fetched
only for user-selected expiries, not the full chain).

## 3. What the API reports

- The session **starts and connects successfully** — `blpapi`'s session is up
  and `is_connected()` returns **True**. So login, `bbcomm`, port `8194`, and
  network are all fine.
- **Every `ReferenceDataRequest` comes back with a `responseError`** (no field
  data at all). The verbatim error is:

```
Request failed on //blp/refdata::ReferenceDataRequest - Bloomberg responseError:
  source=rsfrdsvc2; category=LIMIT; code=-4002;
  subcategory=WORKFLOW_REVIEW_NEEDED; message=Workflow review needed. [nid:24137]
```

- It is **100% reproducible** on every request. The `source` rotates between
  `rsfrdsvc2` / `rsfrdsvc3` and the `nid:` value changes per request (e.g.
  `24137`, `21937`), but the `category=LIMIT`, `code=-4002`,
  `subcategory=WORKFLOW_REVIEW_NEEDED` triple is constant — including for the
  most trivial possible request (`PX_LAST` on `SPY US Equity`).

## 4. What we've already ruled out

- **Not connectivity/login** — the session connects; `is_connected()` is True.
- **Not a bad field or security** — it fails identically on `PX_LAST` for
  `SPY US Equity`, a universally-available field/security.
- **Not request size / rate** — it fails on the very first single-security,
  single-field request of a session.
- **Not the wrapper** — these are plain blpapi `//blp/refdata` requests; the
  error originates from the Bloomberg back-end service (`rsfrdsvc*`), not the
  client.

## 5. Questions for the desk

1. **What is the `WORKFLOW_REVIEW_NEEDED` gate?** We receive `category=LIMIT`,
   `code=-4002`, `subcategory=WORKFLOW_REVIEW_NEEDED` on every `//blp/refdata`
   `ReferenceDataRequest`. What does this state mean and what is it blocking?
2. **What approval clears it, and who initiates it** — is this a
   **compliance / entitlement review** that our firm's Bloomberg administrator
   or compliance officer must approve, and where in the Terminal is that done
   (e.g. `WAPI`, `DAPI`, or an entitlements workflow)?
3. **Is it tied to a specific entitlement** — Desktop API (DAPI) data-access
   entitlement, an app/B-PIPE authorization, or a per-user request-review policy
   that was newly applied to this login?
4. **Confirmation & timing** — once approved, how do we confirm it's cleared,
   and how long does it typically take to propagate to the Terminal session?
5. Is there anything we must run **on the Terminal side** (e.g. an `API<GO>` /
   `WAPI<GO>` acknowledgement or a Data Access Agreement prompt) to complete the
   workflow?

## 6. One-line reproduction they can match

> "Single blpapi 3.26.5.1 Desktop API session to a local Terminal. Session
> connects. A `ReferenceDataRequest` for `PX_LAST` on `SPY US Equity` returns
> `responseError category=LIMIT code=-4002 subcategory=WORKFLOW_REVIEW_NEEDED
> ('Workflow review needed')` from `rsfrdsvc2/3`. Reproducible on every refdata
> request. What workflow approval clears this and who must perform it?"

---

## Plain-language summary

`WORKFLOW_REVIEW_NEEDED` is Bloomberg's way of saying *"API data access for this
login is pending a compliance/entitlement approval."* It is an account-side gate
— no code change on our end can release it. Once the firm's Bloomberg
administrator / compliance approves the workflow, the **same code** starts
returning data and the app's Bloomberg source goes green automatically (the
`feed_status` probe reads the real reason, so the Data Source light flips on its
own). See [`bloomberg_setup.md`](bloomberg_setup.md) for how to verify.
