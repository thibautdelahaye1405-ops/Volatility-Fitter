"""Offline bench: the Massive WS parse + book-apply throughput (no socket).

Generates frames in the Polygon shape ({"ev":"Q","sym":"O:...","bp":..,"ap":..,"t":ns})
batched N events per frame (the cluster batches several events per text frame),
then times massive_ws._parse + LiveBook.apply — the ceiling of what one
Python thread can ingest, independent of the network. Also times a
_chain_from_book-style read: quote() lookups over C contracts.
"""
import json, random, time, sys
from volfit.data.massive_ws import LiveBook, _parse

random.seed(1)
C = 30_000  # distinct contracts (SPX-sized universe)
syms = [f"O:SPY2609{random.randint(1,30):02d}{'C' if i%2 else 'P'}{500000+10*i:08d}" for i in range(C)]
def frame(n):
    evs = [{"ev": "Q", "sym": syms[random.randrange(C)], "bp": round(random.uniform(0.5, 50), 2),
            "ap": round(random.uniform(0.5, 50), 2), "bs": 10, "as": 12, "t": 1758600000000000000 + random.randrange(10**9), "q": 1, "x": 302}
           for _ in range(n)]
    return json.dumps(evs)

for batch in (1, 10, 100):
    frames = [frame(batch) for _ in range(max(2000, 200_000 // batch))]
    total = len(frames) * batch
    book = LiveBook()
    t0 = time.perf_counter()
    for raw in frames:
        book.apply(_parse(raw))
    dt = time.perf_counter() - t0
    print(f"batch={batch:>3} events/frame: {total:>7} events in {dt:6.3f} s -> {total/dt:>9,.0f} events/s ({len(frames)/dt:,.0f} frames/s); book size {book.size():,}")

# read side: quote() lookups for a full chain build (SPY-sized 14k / SPX-sized 30k)
for n in (2_000, 14_000, 30_000):
    t0 = time.perf_counter()
    for s in syms[:n]:
        book.quote(s)
    dt = time.perf_counter() - t0
    print(f"book.quote() x {n:>6}: {dt*1e3:7.2f} ms  ({dt/n*1e6:.2f} us/lookup, one lock acquire each)")
