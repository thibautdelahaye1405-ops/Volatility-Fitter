# Three Priors for a Dark Universe

**Note 14 — graph smile-extrapolation and the assertion dial · lecture edition ("three priors for a dark universe") · converted from 14_graph_three_priors.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

*Graph smile-extrapolation and the assertion dial: smoothness, contracts, dependencies — one solver family, three statements about what the desk is willing to claim. Vol-Fitter Technical Notes, No. 14.*

> **Abstract.** The Vol-Fitter's headline differentiator is filling a mostly-dark universe of smiles — one node per $(\text{underlying},T)$ — from a handful of lit calibrations. This note is the account of *how*, told as a choice the desk must make rather than a single algorithm it must accept. The production solver ships three propagation modes, and they are not three tunings of one idea: they are three different priors, ordered by how much structure the desk asserts about the dark universe. **Smooth field** asserts only smoothness — a screened directed-Laplacian Gaussian field, the classical mathematics of harmonic extension and Tikhonov regularization, the fewest claims to defend, the family's strongest *daily* measured record, and — since the 2026-07-27 flip — the byte-locked rollback and wire default rather than the holder of the desk-facing one. **Messages** asserts relations — every edge a Gaussian contract $z_i\approx\beta z_j$ at a stated precision, the cleanest static probabilistic semantics in the family: full-amplitude transfer regardless of confidence, precision-weighted voting, distance taxing confidence but never the mean, a global information-form solve that never counts a source twice. **Layered** asserts dependencies — the desk's native tongue, and the destination of the family: directed influence arcs cut at the source, a persistent idiosyncratic residual with a half-life, hard Dirichlet clamps on certified fresh marks, and a reciprocal beta-harmonic completion — a prior over *trajectories*, not just over today's field, flexible up to rigid one-way dependency. It is the only prior in the family under which the marks a trader would make by hand are the marks the solver makes, and the containment is literal: switch off its directed and temporal layers and what remains *is* the message operator; decline the contracts too and what remains is the smoothness belief. A single asynchronous two-asset story separates the three in four snapshots: only the layered prior can produce the desk path (a $-3$-point idiosyncratic dislocation that survives the source's next tick), and the note derives why the other two *cannot* — not as defects, but as exactly the assertions they decline to make. Every mean-semantics behaviour quoted here runs through the production solver and is locked by a golden test; every empirical level is read from stored study artifacts; and the mode question itself is adjudicated by pre-registered gates whose recorded verdicts are quoted honestly — both of them, for the target regime has now been scored. At the daily granularity the layered spatial solve carries the family's only measured edge in the stressed regimes — exactly where books bleed — while day-old residual memory does not pay. And on the intraday async replay the mode's central mechanism is *validated*: the residual memory has an interior optimum near a tenth of a day, with per-bucket skill decaying exactly as the OU prior predicts — the daily harness's "memory never pays" was a horizon artifact, as this note argued it would be. What the same replay also shows, and this note reports with equal honesty, is that the message operator's reciprocal carrier outruns every layered arm on that universe: the recorded decision is the mechanism validated, adoption held, and a NAMES campaign — where directedness should finally earn its cut — on the books.

## 1. A universe, mostly dark

The desk owns a universe of smiles, and on any given morning only a few of them are richly quoted. The production spine that serves every node is fixed and worth stating in one breath, because all three propagation modes live inside it. Each node receives a *transported prior* baseline (Note 13's saved prior, moved to today's forward under the spot-dynamics regime of Note 12, through a strict provenance hierarchy with data-derived precision tiers); each *lit* node contributes the innovation $d=\text{calibrated}-\text{transported prior}$ — a genuine market-versus-prior move, fitted in pure-market mode; the graph spreads those innovations to the dark nodes as a posterior increment field $\widehat z$ with a marginal uncertainty; and each dark node's absolute handles $h^0+\widehat z$ retarget into Note 01's arbitrage-free smile machinery, with the functional posterior band and the idiosyncratic ATM band floor carrying the uncertainty into the drawn smile. Residual dark quotes may score a reconstruction afterwards — never steer it. The carrier is the compact handle triple $(\sigma_0,s_0,\kappa_0)$ — ATM vol, skew, curvature — solved as three independent fields.

The interesting question is the middle of that spine: *by what rule do lit innovations reach dark nodes?* This note's answer is that there is no single right rule — there is a dial. At one end the desk asserts almost nothing ("moves are smooth across related smiles") and receives the classical mathematics of harmonic extension in return. At the other end the desk asserts a full dependency structure ("this name follows that index, one way, with a beta I will state, and its own dislocations persist until they decay") and receives, in return, marks that behave the way a trader marking by hand would make them behave. Between the two sits the contract mode: pairwise relations with stated amplitudes and stated trust, and nothing more. The three positions of the dial are the three shipped propagation modes, they share one seam (same universe, same baselines, same innovations, same reconstruction), and the fork between them is a single explicit setting.

> **Invariants protected in this note.**
> 1. A dark node stays at its transported prior unless lit data forces a move; a component with no active observation path keeps zero innovation, honestly broad bands, and an explicit flag — no invented signal, ever, in any mode.
> 2. Reported confidence is always the *marginal* posterior uncertainty, never a conditional; it widens with graph distance and with informer uncertainty.
> 3. Amplitude and trust never mix: in every mode, scaling how much a relation is *believed* must not change how large the implied move *is* — trust prices bands, amplitude prices means.
> 4. One source is one source: however many routes carry it, the solve prices them jointly — precision never accrues by path counting.
> 5. Direction, where asserted, is structural: a layered influence arc is cut at its source — no reverse leakage, by construction, not by penalty.
> 6. The output retargets into the arbitrage-free smile machinery of Note 01; the graph never emits a raw curve.
> 7. Mode and default changes are explicit and evidence-gated: a default moves only on *recorded* held-out evidence, and the record that moves it may be a different horizon than the gate that was written — as on 2026-07-27, when the failed daily gate stayed on the record and the options default moved on the intraday separation ("Evidence and the gates"). Every mean-semantics behaviour in this note is locked by a golden test against a brute-force reference.

**Conventions and the notation ledger.** Node indices $i,j$; the *receiver* of a relation is $i$, its *informer* (or, in the layered mode, its *source*) is $j$, and every ordered object reads "$j$ informs $i$". One time symbol $T$ (maturity, years); calendar time within a session is $t$ and an elapsed interval is $\Delta$. Innovations $z$ are quoted in the receiving handle's units; ATM-vol units are scaled so that $0.01$ is one vol point. Differentiation never appears; all operators are finite-dimensional. The three modes share one ledger — no symbol is reused with a second meaning.

| Symbol | Meaning |
|---|---|
| $z,\ d,\ h^0$ | innovations; lit observations; baseline |
| $\beta_{ij},\ p_{ij}$ | relation amplitude; precision |
| $Q_{\mathrm{sm}},\ Q_{\mathrm{msg}},\ Q_{H}$ | the three precision operators |
| $q_i=\sum_j p_{ij}$ | receiver conditional precision |
| $\kappa$ | anchor/screen toward zero |
| $\alpha_T,\ \rho$ | amplitude shape; class level |
| $K,\ \pi$ | trust kernel; mass ("Assert smoothness: the smooth field") |
| $g_i$ | gauge/harmonic scale ($\beta_{ij}=g_i/g_j$) |
| $u_i,\ \phi_i(\Delta),\ H$ | residual; persistence; half-life |
| $W(\Delta)$ | residual process variance |
| $m^D_i,\ V^D_i,\ e_i$ | directed prediction; residual measurement |
| $\chi_i$ | residual-surprise diagnostic |
| $\Omega,\ V_S$ | widened factor covariance; lit covariance |
| $r_s,\ p^0_i$ | observation / baseline precision |
| $Q^+,\ \Sigma^+,\ G$ | posterior information; covariance; gain |
| $s_i$ | systematic (parent) predictor |

*Table 1 — Every symbol in the note. $p$ is always a relation's precision; baseline precision is $p^0$, never bare $p$; the Kalman-style process variance is $W$, never $Q$, because $Q$ is reserved for precision operators.*

## 2. A morning's story: the asynchronous pair

Before any operator is written down, here is the problem the desk actually has, in the smallest example that contains all of it. Two assets: $A$ is liquid and refreshes every unit of time; $B$ is thin. The desk believes $B$ follows $A$ one-for-one — $\beta_{B\leftarrow A}=1$ — and believes the influence runs one way: $A$ is the market; $B$ is a satellite. Snapshots are produced every half unit. The tape (in handle levels, for exposition; production runs the identical arithmetic on innovations against transported baselines):

$$
A:\ 10,11,12,13,14,15\ \text{at}\ t=0,1,2,3,4,5;\qquad
B:\ 10\ \text{at}\ t=0,\quad 10\ \text{at}\ t=3.5 .
$$

What should the published marks do? Walk it as a trader would. From $t=0$ to $t=3$, $B$ is dark and nothing distinguishes it from its $A$-driven prediction, so it rides the relation: $B$'s mark climbs with $A$ through $10,11,12,13$. At $t=3.5$, $B$ prints at $10$ while the freshest $A$ information is its $t=3$ calibration at $13$. The print is a fact and must be published unmoved. It also *teaches* something: relative to the $A$-driven component, $B$ now carries an idiosyncratic dislocation

$$
u_B \;=\; 10-\beta\cdot 13 \;=\; -3\ \text{points}.
$$

And when $A$ ticks to $14$ at $t=4$ with $B$ dark again, the desk does not throw that dislocation away: $B$'s mark should be $\beta\cdot14+u_B=11$ — following $A$'s move at full amplitude *from its own dislocated level*. The full path is the staircase of Figure 1A, and it is worth being precise about its three load-bearing properties, because each one is an *assertion*, and the three assertions are exactly what separates the three propagation modes.

- **Direction.** $B$'s surprising print revised $B$'s state only. The desk did not mark the S&P down because one satellite came in cheap; there is no $B\to A$ channel at all. This is not a soft preference — it is a structural claim: *influence flows one way*.
- **Memory.** The $-3$-point dislocation observed at $t=3.5$ persisted after $B$ went dark again. A snapshot-by-snapshot solver, however sophisticated, cannot produce the $t=4$ mark of $11$: at $t=4$ its inputs contain no $B$ observation at all. The desk is asserting that *an observed idiosyncratic state is part of today's information*, with its own decay clock.
- **Rigidity.** At $t=3.5$ the print was published exactly, and between prints $B$ tracked $\beta A$ exactly. The desk asserts the relation at full force — conditional on asserting it at all — and asserts that a certified fresh mark is a boundary condition, not a suggestion.

**Why the memoryless answer is not a smaller version of the same thing.** It is tempting to think a static solver merely smooths the same path. It does not — it produces a *different, worse* path, and the mechanism is instructive. A symmetric memoryless field solver, run at each snapshot on whatever is lit at that instant, does three things the desk just declined to do (Figure 1B, run through the production smooth-field solver): at $t=3.5$, with only $B$ lit, the strong $A\!-\!B$ coupling drags the temporarily dark $A$ down toward the satellite's print ($A$'s published mark falls to $10.0$); at $t=4$, with only $A$ lit, the solve has no record that $B$ ever disagreed, so $B$ snaps to $14.0$ — the dislocation is erased by the next source tick; and both behaviours follow from one root cause: *a joint Gaussian field conditioned per snapshot has neither direction nor memory*. Nothing is broken in the algebra. The solver answered exactly the question it was asked — "what smooth field explains this instant's lit marks?" — and the desk was asking a different question.

**Why no constant beta rescues it.** Could the desk instead have wanted a softened path — say $B=10.5$ at $t=4$, splitting the difference? Then the $t{=}3.5\to4$ transition requires $10+\beta(14-13)=10.5$, i.e. $\beta=0.5$; but continuing to $t=5$ at the same logic, $10+\beta(15-13)=11.5$ requires $\beta=0.75$. No constant amplitude produces both — the "softened" path is not a beta, it is a *decaying residual*: exactly the mean-reverting state $u_B(t)=u_B\,2^{-(t-3.5)/H}$ of "Assert dependencies: the layered dynamic-harmonic mode", with a finite half-life $H$. (A conventional mean reversion $0\le\phi\le1$ can only make $B$ catch *up* to $A$ faster — it can never explain a $t=4$ mark below $11$; the flat staircase of Figure 1A is the long-half-life limit.) The same observation kills the tempting implementation shortcut of measuring $B$'s residual against an *interpolated* $A$ value at $t=3.5$: interpolating $A$ between $13$ and $14$ uses $A$'s *future* print, and a live system cannot look ahead. Causality forces last-tick alignment.

> **Figure 1 — The asynchronous pair (figure not included in this pack).** The asynchronous pair, and the assertion that separates the modes. A: the desk path, replayed through the production layered state machinery (source lease carried flat between prints, hard residual update at the $t=3.5$ print, dislocation persisting until the next actual $B$ observation) — the replay reproduces the golden acceptance sequence exactly. B: the same tape pushed through the production smooth-field solver snapshot by snapshot: at $t=3.5$ the satellite's print drags the dark source down (no direction), and at $t=4$ the dislocation is erased by the next source tick (no memory). The second panel is not a bug — it is the correct answer to a weaker question. *Panel A shows the desk staircase: $B$'s mark riding $\beta A$ through $10,11,12,13$, resetting hard to $10$ at the $t=3.5$ print, then following $A$ from its dislocated level to $11$ at $t=4$ and $12$ at $t=5$, with $A$'s own marks untouched throughout. Panel B shows the memoryless smooth-field replay of the same tape: $A$'s published mark is dragged down to $10.0$ at $t=3.5$ when only $B$ is lit, and $B$ snaps to $14.0$ at $t=4$ when only $A$ is lit — the $-3$-point dislocation erased. The quantitative takeaway: the two paths differ by the full dislocation at $t=4$ ($11$ versus $14.0$), and no tuning of the static solver reproduces the desk path.*

**The dial.** Now the note's organizing claim can be stated plainly. The three propagation modes are three priors, ordered by how much of the story above the desk asserts:

| Mode | Asserts | Mean semantics | Direction | Memory |
|---|---|---|---|---|
| Smooth field | smoothness only | emergent | none | none |
| Messages | relations | contractual, exact | symmetric | none |
| Layered | dependencies | contracts $+$ clamps | cut at source | half-life state |

Each column purchase has a price. The smooth field's modesty is why it is the easiest mode to defend when nothing is configured — and why its propagation behaviour is emergent rather than promised. The message mode's contracts make every desk sentence a theorem of one static Gaussian — and a static symmetric Gaussian is constitutionally unable to express the story's direction or memory ("Assert relations: precision messages" derives this, not just states it). The layered mode is the only position of the dial that speaks the whole story, and the other two are its truncations rather than its rivals: switch off memory, direction and clamps and the layered mode's reciprocal layer is literally the message operator; decline even the contracts and what remains is the smoothness belief. Speaking the whole story is paid for in state — persistence brings causality discipline, invalidation rules, and an adjudication question ("does carried memory actually predict?") that "Evidence and the gates" answers with recorded numbers rather than enthusiasm. The next three sections climb the dial in order of increasing assertion, each with the same contract: say precisely what is assumed, derive what that buys, and show the production solver doing it. Read them as an ascent: each position keeps everything the one below it earned, and buys back one more property of the desk path.

## 3. Assert smoothness: the smooth field

The first position of the dial asserts the minimum a graph can assert: *related smiles move similarly*. No amplitudes are promised, no directions, no memory — just a preference for fields that are small and neighbour-consistent. The reward for such modesty is that the entire classical apparatus of smoothing applies, and every object below is a standard one: a Markov kernel, a Dirichlet-type energy, a screened Laplacian, a Gaussian-process update.

The desk (or the auto-lattice) supplies raw nonnegative weights, read "$j$ informs $i$". Row-normalization turns them into a row-stochastic *trust kernel* $K$ ($\sum_jK_{ij}=1$): trust in this mode is *relative* — a receiver distributes one unit of attention over its informers. A stationary mass $\pi$ ($\pi^{\mathsf T} K=\pi^{\mathsf T}$) prices each node's importance in the traffic of the graph. The increment field then receives the Gaussian prior $z\sim\mathcal N(0,Q_{\mathrm{sm}}^{-1})$ with

**Central equation.**

$$
Q_{\mathrm{sm}}=D_\kappa+\eta\,L_{\mathrm{dir}}^{\beta}+\lambda\,(A_{\rho}+\nu I)^{-1},
\qquad
L_{\mathrm{dir}}^{\beta}=(I-K\!\circ\!\beta)^{\mathsf T}\,\Pi\,(I-K\!\circ\!\beta),
\tag{1}
$$

a three-member committee. The first member, $D_\kappa=\operatorname{diag}(\kappa)$, charges every node for moving alone — it is what makes the prior proper, and it is the same "anchor toward zero innovation" object $\kappa$ that will reappear in both other modes. The second member charges node $i$ at its importance $\pi_i$ for the part of its move its informers did not predict, $z_i-\sum_jK_{ij}\beta_{ij}z_j$: a directed *prediction* residual, PSD for any real amplitude matrix $\beta$ since it is a Gram matrix in the $\Pi$-weighted inner product. The third member (shipped off, $\lambda=0$) prices a move by the cheapest mass flux that could have transported it along the graph — the tangent norm of unbalanced optimal transport, read through its dual as a screened Poisson problem. The lit innovations then condition this prior in covariance form (the Gaussian-process update, exact, with baseline precision folded in), and the reported confidence is the reciprocal of the *marginal* posterior variance — never the diagonal of the posterior precision, which answers the wrong (conditional) question and overstates confidence precisely at the dark nodes whose neighbours are themselves uncertain.

What does this buy? Figure 2A shows the production solve on a calendar chain with one lit node: the innovation propagates outward and *decays*, the marginal band widening with distance — with $\eta$ controlling the reach (Figure 2B): small $\eta$ and the $\kappa$ member wins (moves stay local); large $\eta$ makes unexplained neighbour disagreement expensive and the move travels. This is the signature smooth-field behaviour, and it is worth contrasting with what is coming: *decay of the mean with distance is a feature of the smoothness assertion*, not of graph propagation as such. (The decay is not even monotone: at the shipped reach the far node receives essentially nothing — $-3$% of the lit move, a small overshoot below zero, because the directed residual energy is not an M-matrix interpolant — while at $\eta=60$ the transfer reaches 21%.) The message mode will make the opposite promise (full amplitude at any distance, with the band paying the toll), and both promises are internally consistent — they answer different questions.

> **Figure 2 — The smoothness prior at work (figure not included in this pack).** The smoothness prior at work (production solver, eight-node calendar chain, one lit node at $+1$). A: the posterior mean decays with graph distance while the marginal band honestly widens — essentially none of the move survives to the far node ($-3$%, a small overshoot of zero), the sd growing from 0.10 at the lit node to 1.80 at the far end. B: the reach dial: the directed-smoothness weight $\eta$ sets how expensive unexplained neighbour disagreement is, and therefore how far a move travels (21% at $\eta=60$). Decay-with-distance is the smoothness assertion itself, not a law of graph propagation. *Panel A plots the posterior mean and marginal band along the eight-node chain: the mean falls from the lit $+1$ toward zero with distance, ending at $-3$% of the lit move at the far node (a small overshoot below zero, the non-M-matrix signature), while the standard deviation grows from 0.10 at the lit node to 1.80 at the far end. Panel B sweeps the reach dial $\eta$ and plots the far-node transfer: near zero at the shipped stiffness, rising to 21% at $\eta=60$. The takeaway: under the smoothness prior, both how far a move travels and how much arrives are emergent consequences of coupled dials, not promised amplitudes.*

Three honest properties complete the picture, each a direct consequence of asserting only smoothness. *Semantics are emergent*: because trust is row-normalized, adding an informer redistributes attention — reach, stiffness and anchoring share coupled dials, and there is no per-relation sentence of the form "this edge transfers $+2$ at trust $p$". *Inference is symmetric*: the posterior precision is symmetric, so a satellite's print legitimately pulls an uncertain source — panel B of Figure 1 showed exactly this, and within this mode's contract it is *correct*: absent any directional assertion, evidence flows both ways. *There is no state*: the solve is a function of this snapshot's lit set. None of these is a defect; each is the absence of an assertion the desk chose not to make. And the mode carries the strongest measured record in the family precisely because it claims so little: on the stored benchmarks, dark single names behind lit indexes and ETFs gain $+7.9$ to $+14.2$ ATM vol bps in the August-2024 spike regime and $+3.8$ to $+7.2$ fully out-of-sample in the October-2022 bear, with calm-regime skill $+0.7$ to $+0.8$ — never negative — and calm-regime dark-name bands made honest by the idiosyncratic ATM floor ($\operatorname{std}\zeta$ $1.91\to1.02$ and $1.85\to1.03$). It held the desk-facing default for the project's whole history, and "Evidence and the gates" shows both the gate that kept it there and the intraday evidence that finally moved it; it remains the wire default and the byte-locked rollback.

> **Heuristic.** The smooth field is the mode of *least commitment*: a maximum-entropy flavoured answer to "I believe these smiles are related but will not say how much or which way". Its mathematics is the oldest and best understood in the family — harmonic extension, Tikhonov, Gaussian-process regression — and least commitment is a genuine virtue when nothing has been asserted; but the auto-lattice means a relation structure is in fact always configured, and the intraday replay priced the modesty: at day-scale stiffness the zero-innovation anchor shrinks intraday innovations to almost nothing, and the field mode measured nearly inert exactly where the desk works ("Evidence and the gates"). It remains the wrong tool when the desk has a sentence like "B follows A, one way, beta one" that it wants *obeyed*. It is the ceiling of what an unconfigured solver can know — and a desk that never accumulates such sentences is not exercising modesty, it is leaving information on the table. The rest of the dial exists for the day the desk starts talking.

## 4. Assert relations: precision messages

The second position of the dial asserts *relations*: for each configured pair, a sentence with two independent clauses — how large the implied move is, and how much the relation is trusted. The mode's whole design is that these sentences are *contracts*: every desk-facing behaviour below is a theorem of one joint Gaussian, locked by a golden test, and none of them can drift without a named test failing.

**Definition 1 (Message edge).** A relation from informer $j$ to receiver $i$ consists of a conditional relation precision $p_{ij}>0$, a per-handle amplitude triple $\beta_{ij}$, and a relation class (calendar, broad index, sector ETF, sector peer, custom). Its meaning is the Gaussian statement

$$
z_i=\beta_{ij}\,z_j+\epsilon_{ij},
\qquad \epsilon_{ij}\sim\mathcal N(0,\,1/p_{ij}):
$$

*amplitude says what the receiver's move should be; precision says how much the relation is trusted. They never mix.*

Each relation contributes one rank-one Gaussian factor, and the operator is their sum:

**Central equation.**

$$
Q_{\mathrm{msg}}=\sum_{(j\to i)}p_{ij}\,u_{ij}u_{ij}^{\mathsf T},
\qquad
u_{ij}=e_i-\beta_{ij}e_j,
\qquad
q_i=\sum_j p_{ij}.
\tag{2}
$$

Positive semidefiniteness is immediate for arbitrary real betas (a sum of PSD rank-one terms), and the assembly is sparse by construction — each factor touches two nodes.

**Proposition 1 (Receiver conditional).** Minimizing the factor energy over $z_i$ with the informers held fixed gives

$$
z_i\mid\{z_j\}\sim\mathcal N\!\left(
\frac{\sum_jp_{ij}\beta_{ij}z_j}{q_i},\ \frac{1}{q_i}\right).
$$

Incoming messages are precision-weighted and *averaged*; independent incoming conditional precisions *add*.

*Proof.* The terms of equation (2) containing $z_i$ are $\sum_jp_{ij}(z_i-\beta_{ij}z_j)^2$; completing the square in $z_i$ gives the stated mean and variance. ∎

This one line is the entire desk semantics, and Figure 3 shows its sharpest consequence through the production solve: on the three-expiry ladder (3M/6M/1Y, 6M lit $+1$ vol point, $\alpha_T=1$) the dark receivers land at exactly $\widehat z_{3M}=+2.00$ and $\widehat z_{1Y}=+0.50$ for *every* edge precision across three decades, while the posterior standard deviation scales as $p^{-1/2}$. Amplitude is not a function of confidence — two dials, because two fields. Contrast this directly with Figure 2: where the smoothness prior made distance decay the mean, the contract prior forbids it — along a chain amplitudes multiply while variances accumulate,

$$
\mathbb E[z_C]=\beta_2\beta_1\,\mathbb E[z_A],
\qquad
\operatorname{Var}(z_C)=(\beta_2\beta_1)^2\operatorname{Var}(z_A)
+\frac{\beta_2^2}{p_1}+\frac{1}{p_2},
\tag{3}
$$

and *no mean haircut is ever applied for distance* (Figure 4): the mean crosses six hops undamped (production: $\widehat z=1.000$ at hop six) while the band pays the toll, the production marginals matching the accumulation identity to 0.0000 exactly.

> **Figure 3 — The contract (figure not included in this pack).** The contract, run through the production operator and posterior (three-expiry ladder, 6M lit $+1$ vol point). A: the dark receivers' posterior means sit at the configured amplitudes $+2$ and $+0.5$ regardless of edge precision. B: what the precision *does* control — the posterior standard deviation, falling as $p^{-1/2}$. Confidence and amplitude are separate dials because they are separate fields of the edge. *Panel A plots the posterior means of the 3M and 1Y dark receivers against edge precision swept over three decades on a log axis: both traces are exactly flat, at $+2.00$ and $+0.50$ vol points. Panel B plots the corresponding posterior standard deviations, falling along the $p^{-1/2}$ line. The takeaway: precision moves only the band; the mean is the contract.*

> **Figure 4 — Multi-hop propagation under the contract prior (figure not included in this pack).** Multi-hop propagation under the contract prior (production solve, six-hop chain, $\beta=1$): the posterior mean crosses every hop undamped while the marginal band accumulates exactly the per-edge relation variances of equation (3) (dotted: the closed-form accumulation). Distance costs confidence, never amplitude — the exact opposite of the smoothness prior's signature, and both are correct answers to their own questions. *The figure plots posterior mean and marginal band by hop index along a six-hop unit-beta chain lit at one end with $+1$: the mean is flat at 1.000 through hop six, while the band widens hop by hop, sitting exactly on the dotted closed-form variance accumulation of equation (3) — the production marginals match it to 0.0000. Read beside Figure 2A, the two panels are the two priors' opposite signatures on the same geometry.*

### 4.1 Why factors, not averages: the dead informer

There is a natural-looking alternative assembly one should examine before trusting equation (2) — and its failure is the sharpest illustration of what "the joint form is a modelling decision" means. Normalize each receiver's incoming precisions into weights $p_{ij}/q_i$ and charge the receiver once for deviating from its precision-weighted forecast, $q_i\,(z_i-\sum_j(p_{ij}/q_i)\beta_{ij}z_j)^2$ — the same shape as the smooth field's directed residual. Both assemblies produce the *identical* receiver conditional of Proposition 1, so no local example can tell them apart. They differ in the joint distribution, and the difference has teeth.

> **Case file — the dead informer.**
>
> **Setup.** A receiver hears two informers at equal configured precision: one lit, one *dead* — a dark dead-end with no lit path and no other relations. What should the lit message transfer?
>
> **The contract answer.** Everything: the dead informer carries no information, so configuring trust in it must cost nothing. In the pairwise form this is automatic — marginalizing an unconstrained informer removes its factor exactly (the Gaussian integral over a free $z_j$ of $p\,(z_i-\beta z_j)^2$ is flat in $z_i$) — and the production solve transfers 1.00 of the lit message across four decades of dead-informer precision (Figure 7A), the dead node simply riding along with a broad marginal.
>
> **The averaging answer.** In the row-normalized form the weights are fixed by *configured* precision whether or not an informer carries information: the residual can be zeroed for any $z_i$ by moving the free informer, the posterior is improper, and under a small regularizing anchor the receiver transfers only 0.40 of the lit message at equal precisions — decaying toward zero as the dead informer's configured precision grows. Configuring trust in a silent neighbour *destroys* a live signal.
>
> **Two more properties settle the form.** A reciprocal bidirectional pair collapses to *one* factor, so auto-generated calendar relations cannot double-count precision; and the factor list *is* the sparse assembly — no normalization couples edges into the same receiver. *The joint form of an operator is a modelling decision even when every local conditional agrees.*

The convention that makes one-factor-per-relation well defined is the **canonical orientation**: $p\,(z_i-\beta z_j)^2$ and $p'\,(z_j-z_i/\beta)^2$ are the same factor iff $p_{j\leftarrow i}=p_{i\leftarrow j}\,\beta^2$ — the reverse reading of one contract, in the informer's units. Auto calendar relations are therefore quoted with the *shorter* maturity as receiver — relation noise in short-dated vol units, where moves are largest and desk intuition lives — with implied reverse amplitude $1/\beta$; the receiver diagnostic $q_i$ maps every incident factor into $i$'s units by the same identity. Explicit user relations stay directed as entered; entering both directions deliberately creates two distinct relations, and the cycle diagnostics of "The accountant: the information-form posterior" apply. Note carefully what the reverse identity says about the dial: *a symmetric factor read backwards is just as precise* — a beta-one high-precision contract between $A$ and $B$ is high-precision in *both* directions. The message mode cannot express "$A$ informs $B$ and never conversely"; the UI arrow sets units and bookkeeping, not causality. Where strictly one-way conditioning is required, the graph must either clamp the source (only while it is fresh) or move to the layered mode, whose influence arcs are cut structurally ("Assert dependencies: the layered dynamic-harmonic mode"). This is the precise seam between the second and third dial positions — and it is a seam, not a wall: the layered mode's reciprocal layer reuses the message factor *unchanged* ("The harmonic completion"), so everything configured in this section — contracts, precisions, amplitude levels, the gauge — carries up the dial intact. Moving to layered costs nothing already built; it adds the three assertions this mode cannot make.

### 4.2 Amplitude: shape locked, level measured

For a calendar relation the amplitude is the maturity shape

$$
\beta_{i\leftarrow j}=\Big(\frac{T_j}{T_i}\Big)^{\alpha_T},
\qquad \alpha_T=1\ \text{(default, per-handle configurable)},
\tag{4}
$$

constant total-variance injection — a $+1$ vol-point move at 6M reads as $+2$ at 3M and $+0.5$ at 1Y — and reciprocal by construction: $\beta_{i\leftarrow j}\beta_{j\leftarrow i}=1$, so a ladder cannot claim amplification both ways. On stored data the shape is *weakly identified* at the day horizon ($R^2$ 0.180 vs 0.181 across $\alpha_T\in\{0,1\}$ once the level refits), so $1.0$ is held by its semantics and the adjudication campaigns sweep it.

Full-force transmission is the correct semantics *conditional on a relation the desk asserts*. It is not what the tape does on average: on ~11735 stored adjacent-pair observations the realized day-over-day calendar transfer under the $\alpha_T=1$ shape is 0.23 per unit of predicted move, and the one-source index→name transfer is 0.391. A default transmitting at full force would fail the pre-registered RMS gate on its first day. So amplitude splits: the *shape* stays locked, and the *level* is a per-relation-class multiplier $\rho\in(0,1]$ with two presets — `desk` ($\rho=1$, full force, the belief mode) and `learned` (the measured levels; they are shape-dependent — $0.23$ is the $\alpha_T{=}1$ calendar value, and the $\sqrt T$-shape equivalent is $0.34$).

How should $\rho$ enter? Two natural answers are provably wrong. Scaling the beta ($\beta\to\rho\beta$) shrinks the forward conditional but *amplifies* the reverse one by $1/\rho$ — the reciprocal identity turns attenuation into amplification. Emitting two directed shrunk factors double-counts the relation and composes to $2\rho/(1+\rho^2)\neq\rho$. The consistent mechanization of regression attenuation in both directions of one joint Gaussian is a *local innovation anchor* — the $\kappa$ of the ledger, now derived rather than configured:

$$
\kappa_i=p_{\mathrm{primary}}\,\frac{1-\rho_{\mathrm{class}}}
{\rho_{\mathrm{class}}},
\tag{5}
$$

with $p_{\mathrm{primary}}$ the largest incident relation precision in node $i$'s units and $\rho_{\mathrm{class}}$ that primary relation's class multiplier — *fixed at build time, never rescaled as further edges arrive*. The desk preset $\rho=1$ gives $\kappa=0$ exactly: the belief mode is the pure contract semantics, not a limit.

**Proposition 2 (Corroboration under the node-linked anchor).** With $k$ equal agreeing clamped sources at precision $p$, beta one, and the fixed anchor of equation (5), the receiver's transfer per unit message is

$$
\frac{kp}{\kappa+kp}=\frac{k\rho}{1-\rho+k\rho}:
$$

one source transfers exactly $\rho$; two lift it to $2\rho/(1+\rho)$; independent corroboration keeps raising the effective transfer toward one.

*Proof.* By Proposition 1 the $k$ agreeing messages average to the common value at conditional precision $kp$; the anchor adds a zero-innovation pseudo-message at precision $\kappa$, so the posterior mean shrinks by $kp/(\kappa+kp)$; substitute equation (5). ∎

The fixed anchor is not a preference; it is the mechanization the data chose, through a falsifiable prediction. The alternative — an edge-linked anchor $\kappa_i=\sum_jp_{ij}(1-\rho)/\rho$, under which the transfer is constant at $\rho$ regardless of source count — predicts *no* corroboration lift. The stored benchmark rows adjudicate: across 1007 name-days carrying same-sector peers, the one-source index transfer slope is 0.391 and the measured two-source (index $+$ peer-average) slope is 0.561 — an uplift of $+43\%$ against a pre-registered $15\%$ bar. Calibrating the fixed-$\kappa$ model on the *single-source slope alone* predicts 0.563 for two sources: agreement to 0.3%, with zero free parameters (Figure 5).

> **Figure 5 — Amplitude level as a measured object (figure not included in this pack).** Amplitude level as a measured object (production anchor and posterior; measured points from the stored design-study artifact). The node-linked fixed anchor produces the corroboration curve $k\rho/(1-\rho+k\rho)$; calibrated only on the one-source slope (0.391), it predicts the measured two-source transfer to 0.3% with no free parameters. The edge-linked alternative — constant transfer regardless of source count (dashed) — predicts no lift and is contradicted by the same measurement ($+43\%$ against a $15\%$ bar). *The figure plots effective transfer per unit message against source count $k$: the fixed-anchor curve rises from 0.391 at $k=1$ through 0.563 at $k=2$ toward one, and the measured two-source point at 0.561 sits essentially on it. The dashed horizontal at 0.391 is the edge-linked alternative's no-lift prediction, contradicted by the measured $+43\%$ uplift against the pre-registered 15% bar. Agreement of prediction and measurement is 0.3%, with zero free parameters.*

**Confidence has empirical defaults too.** The calendar precision family is

$$
p^{\mathrm{cal}}_{ij}
=\frac{p_0}{\epsilon_T+\sqrt{|T_i-T_j|}},
\qquad
p_0\approx 1690\ \text{vol}^{-2},\quad
\epsilon_T\approx 0.97\ \sqrt{\text{years}},
\tag{6}
$$

with the seeds fitted on the same stored adjacent-pair residuals (Figure 6B): about 2.7 vol points of relation noise at a one-month gap, and — the honest surprise — *nearly gap-flat* at the day horizon: $\epsilon_T$ dominates, the family degrades gracefully toward constant precision, and whether the decay term earns its keep at all is one of the campaign ablations (`constant` and log-distance families ship beside it). Cross-class seeds from the same study: index→name $p\approx1.3\times10^4$, sector peer $p\approx0.9\times10^4$ (vol units) — with the recorded caveat that both are measured on ticker-day *median* innovations and are therefore upper bounds on per-edge precision. Two unit disciplines complete the picture: edge precision is quoted in ATM-vol units, with the skew and curvature fields scaling it by the squared ratio of the production per-handle move scales — a units choice, not a semantics choice, since the precision-weighted *average* is invariant to a global rescale of all incoming precisions; and variance is the readable coordinate (an edge carries $\operatorname{Var}\epsilon=1/p$), which is what makes the chain identity of equation (3) legible.

> **Figure 6 — The calendar relation, split into its two fields (figure not included in this pack).** A: the amplitude shape of equation (4) — what a 6M move implies elsewhere on the ladder, per exponent; $\alpha_T=1$ (locked) is constant total-variance injection. B: the confidence family of equation (6) against the stored residuals it was fitted on — relation noise is nearly gap-flat at the day horizon, so $\epsilon_T$ dominates and the decay term's keep is an open ablation. *Panel A draws the implied move across the maturity ladder for a $+1$ vol-point move at 6M under several exponents; the locked $\alpha_T=1$ trace reads $+2$ at 3M and $+0.5$ at 1Y. Panel B overlays the fitted family $p_0/(\epsilon_T+\sqrt{|T_i-T_j|})$ with $p_0\approx1690$ and $\epsilon_T\approx0.97$ on binned residual noise from the ~11735 stored adjacent pairs: roughly 2.7 vol points of noise at a one-month gap, and nearly flat in gap — the visual case that $\epsilon_T$ dominates at the day horizon.*

**Exercise 1.** Derive both rejections of the anchor section: (i) show that replacing $\beta$ by $\rho\beta$ in one factor turns the implied reverse-direction amplitude into $1/(\rho\beta)$; (ii) show that two directed factors $p(z_i-\rho\beta z_j)^2+p'(z_j-\rho z_i/\beta)^2$ with matched units produce a one-source transfer of $2\rho/(1+\rho^2)$, not $\rho$. Then verify from equation (5) that $\rho=1$ gives $\kappa=0$ exactly.

### 4.3 The accountant: the information-form posterior

The factors, the anchors and the lit observations assemble in information form, solved per connected component of the factor support:

**Central equation.**

$$
Q^+=Q_{\mathrm{msg}}+D_\kappa+H^{\mathsf T}R_d H,
\qquad
b^+=H^{\mathsf T}R_d\,d,
\qquad
\widehat z=(Q^+)^{-1}b^+,\quad \Sigma^+=(Q^+)^{-1},
\tag{7}
$$

with three honesty rules that are as load-bearing as the algebra. *No lit path, no invented signal*: components are built on $\beta\neq0$ edges (a zero-beta factor couples only its receiver — the reachability guard that stops an information-free informer from destabilizing an observed component); a component with no lit observation is never solved into propriety — it keeps $\widehat z=0$, the transported prior, an explicit flag, and an explicitly broad variance; every observed component is verified positive definite by Cholesky before inversion. *Innovations are only as precise as their ingredients*: a lit innovation is a difference of two estimates, so its observation precision combines harmonically, $r^d_s=\big(1/r^{\mathrm{cal}}_s+1/p^0_s\big)^{-1}$, and the placement rule holds baseline uncertainty to exactly one appearance per node — folded into $r^d_s$ for a lit source, added once to the reconstruction band for a dark node, golden-locked so no node is widened twice. *Attribution is exact*: the gain matrix $G=\Sigma^+H^{\mathsf T}R_d$ decomposes every posterior shift over the observed lit sources, $\widehat z_i=\sum_sG_{is}d_s$, contributions summing to the shift by construction — per independent *source*, never per path, because path contributions are correlated and non-unique.

The accountant's signature behaviours run through the production solve in Figures 7 and 8. Two routes carrying one source are priced jointly: on the triangle fixture (source observed at finite precision $p$, one direct and one two-leg route) the global posterior variance is $1.67/p$, where naive per-message accounting — the equation (3) effective precisions added as if independent — claims $1.20/p$, overstating precision by a factor of $1.39$. Competing messages vote: equal opposing signals cancel to $0.00$ at *doubled* conditional precision $2p$ (disagreement is not silence); a $3p$ source outvotes to $-0.50$; and under $\alpha_T=1$ betas the same $\mp1$ raw signals land at $+0.75$ — not a defect but the contract: signals are mapped into receiver units *before* the vote, and equal-absolute-vol cancellation is a $\beta=1$ statement.

> **Figure 7 — The accountant at work (figure not included in this pack).** The accountant at work (production solves). A: the dead-informer case file — a row-normalized assembly dilutes a lit message toward zero as a silent neighbour's *configured* precision grows; the pairwise factor marginalizes the dead informer away exactly. B: repeated routes from one source — the global posterior variance ($1.67/p$) against naive independent-message accounting ($1.20/p$): path counting would fabricate a $39\%$ precision overstatement. *Panel A plots the transferred fraction of the lit message against the dead informer's configured precision over four decades: the pairwise-factor trace is flat at 1.00, while the row-normalized trace starts at 0.40 at equal precisions and decays toward zero. Panel B compares the target's posterior variance on the triangle fixture: the correct joint $1.67/p$ against the naive independent-route $1.20/p$, a $39\%$ precision overstatement had the routes been priced as independent.*

> **Figure 8 — Competing messages vote (figure not included in this pack).** Competing messages vote (production solves; 6M dark, 3M and 1Y lit at $\mp1$ vol point). Equal precision and $\beta=1$: exact cancellation at doubled conditional precision. A $3p$ source outvotes. Under the locked $\alpha_T=1$ betas the same raw signals map to $-0.5$ and $+2$ in 6M units before averaging — the receiver hears receiver-unit predictions, not raw levels. *The figure shows the 6M receiver's posterior mean under three configurations of the opposing lit informers: equal precisions at $\beta=1$ cancel exactly to 0.00 while the conditional precision doubles to $2p$; a $3p$ informer outvotes to $-0.50$; and the locked $\alpha_T=1$ betas map the $\mp1$ raw signals to $-0.5$ and $+2$ in 6M units before averaging, landing the receiver at $+0.75$. The takeaway: competition is a precision-weighted vote over receiver-unit predictions, never a sum of raw levels.*

Internal consistency of the amplitudes is policed by a gauge argument: a positive beta structure is cycle-consistent — every directed cycle's beta product equals one — iff there exist node potentials $g_i>0$ with $\beta_{ij}=g_i/g_j$ (if $\beta_{ij}=g_i/g_j$, every cycle product telescopes to one; conversely propagate $\log\beta$ along a spanning tree and any closing edge that disagrees exhibits a bad cycle). Production runs exactly this proof as an algorithm — a union-find sweep with logarithmic offsets, linear time — and flags every closing edge whose implied cycle product strays from one (the reference cross-check of Appendix D plants a consistent triangle, zero flags, and an inconsistent one, flagged at product 0.833). Auto calendar ladders are gauge-consistent by construction ($g_i=T_i^{-\alpha_T}$) — and this same potential-function identity will return in the layered mode as the change of variables that turns beta-relations into a plain harmonic problem.

**Exercise 2.** Reproduce panel B of Figure 7 by hand: with the source observed at precision $p$ and all three relation precisions $p$, assemble the $3\times3$ information matrix of equation (7), invert, and show the target's marginal variance is exactly $5/(3p)$, while the equation (3) effective-message precisions ($p/2$ direct, $p/3$ through the middle node) sum to $5p/6$, i.e. variance $6/(5p)$. The naive answer is wrong because both routes share the source's own uncertainty — the covariance the global solve refuses to forget.

**Exercise 3.** Three distinct quantities appear at every receiver: edge precision $p_{ij}$, conditional incoming precision $q_i=\sum_jp_{ij}$, and marginal posterior precision $1/\Sigma^+_{ii}$. Construct a two-node example where $q_i$ is large but the marginal precision is small (an uncertain informer), and one where the marginal exceeds $q_i$ (the receiver's own observation). Only in the idealized clamped-independent-informer case do the last two coincide — which is why the wire reports both, and the desk surface ("One universe, three answers") is explicit that "local $\neq$ final".

## 5. Assert dependencies: the layered dynamic-harmonic mode

The third position of the dial asserts what "A morning's story: the asynchronous pair" showed no static symmetric Gaussian can express: *dependencies*. Three new commitments are made, and each buys back one property of the desk path. Some relations are *influence arcs* — conditional source-to-target equations, cut at the source — rather than reciprocal constraints (direction). Each node owns a *persistent idiosyncratic residual* with its own decay clock (memory). And a certified fresh calibration is a *boundary condition* — its published central value is clamped, not negotiated (rigidity). The mode's name describes its architecture: a directed dynamic *layer* produces predictions that feed a reciprocal *harmonic* completion, and the two layers own different relation classes.

It is worth saying plainly why this section is the note's destination. The three properties of "A morning's story: the asynchronous pair" are not preferences a desk might trade against a basis point of RMS — they are workflow invariants a trading book must be able to defend in an audit: a satellite's print must never mark down the index; a dislocation the desk paid to learn must not evaporate because the index ticked; a certified fresh mark is a fact, not a suggestion. The two priors before this one do not merely *score* differently against those sentences — they cannot *state* them. And the ascent costs nothing already built: every piece of machinery the note has constructed reappears here as a component — the message factor as the reciprocal layer, the gauge potentials as harmonic coordinates, $\kappa$ as the screen, the accountant's one-source-is-one-source covariance discipline at the boundary — so the layered mode is less a third invention than the family completed: the position of the dial at which the solver finally speaks the desk's full language.

### 5.1 State: the residual and the lease

The new primitive is the split of a target's innovation into what its sources explain and what is its own:

$$
z_{i,t}=\beta_{ij}\,z_{j,t}+u_{i,t}+\epsilon_{ij,t},
\qquad \epsilon_{ij,t}\sim\mathcal N(0,1/p_{ij}),
\tag{8}
$$

where $u_i$ — the *idiosyncratic residual* — is a state variable with dynamics

$$
u_{i,t+\Delta}=\phi_i(\Delta)\,u_{i,t}+\omega_{i,t},
\qquad
\phi_i(\Delta)=2^{-\Delta/H_i},
\qquad
\omega_{i,t}\sim\mathcal N\big(0,W_i(\Delta)\big).
\tag{9}
$$

Four controls, four different meanings — and the mode's design discipline is that they never substitute for one another: $\beta$ is the mean response to a source move; $p$ is relation noise; $\phi$ (through the half-life $H$) is how quickly an *actually observed* dislocation is forgotten; $W$ is how uncertain the residual becomes while unobserved. Using edge precision to make an old observation fade would conflate confidence with mean dynamics; using beta to widen uncertainty would conflate amplitude with confidence; the constant-beta computation of "A morning's story: the asynchronous pair" already showed that no amplitude can imitate a decaying residual. The half-life limit $H\to\infty$ ($\phi\equiv1$) is the random-walk default — the flat staircase of Figure 1A — and Figure 11A shows the production state object advancing the $-3$-point dislocation under $H\in\{1,5,20,\infty\}$: what the desk asserts with $H$ is precisely *how long a private dislocation is believed*.

Sources carry state too, in a weaker sense: a recent actual calibration of a liquid name remains the causal source value between expected refreshes — an *observation lease*, with a timestamp, a maximum age, and process variance accumulating since the print. Two disciplines make leases safe. A lease carries the *innovation*, never the absolute level, so a carried node's published mark keeps moving with its transported baseline between observations — carrying levels would silently break transported-prior semantics. And a lease is not a saved output: only states descended from an *actual calibration* are ever persisted — graph-predicted values never re-enter as pseudo-data, the same no-self-feeding invariant every mode obeys, here promoted to a store-level rule.

### 5.2 The directed pass

With sources resolved (fresh, or carried under lease) and residuals advanced to the snapshot time, the directed layer sweeps the influence graph in topological order. A dark target with parents $P(i)$ receives the *systematic prediction* and its honest variance:

**Central equation.**

$$
m^D_i=\sum_{j\in P(i)}\frac{p_{ij}}{q_i}\,\beta_{ij}\,m_j+m_{u,i},
\qquad
V^D_i=a_i^{\mathsf T}\,\Sigma_{P(i)}\,a_i+V_{u,i}+\frac{1}{q_i},
\tag{10}
$$

where $a_i$ collects the coefficients $(p_{ij}/q_i)\beta_{ij}$ and $\Sigma_{P(i)}$ is the *full parent covariance*. That last object is the implementation's quiet centerpiece: the pass propagates each node's value as a linear combination of independent *root* variables (observation innovations, residual states, per-target relation noises), so the covariance between any two nodes — including two targets that share an ancestor — is exact, by bookkeeping rather than by an independence assumption. Two parents carrying the same market factor are not treated as independent merely because two arcs were configured; the attribution rows are the same gains, so contributions sum to the mean by construction, per observed ancestor and per residual, never per path.

Three structural rules complete the layer. *The cut*: when a target is observed, its surprise updates the *target's* residual only — the pass never writes a parent, so a satellite's print cannot revise the index, structurally rather than by penalty (golden-locked as zero reverse influence). *DAG only*: directed cycles are rejected outright — reciprocity is not a cycle's job but the harmonic layer's, and a topological solve buys exact one-way semantics, no spectral-radius condition, deterministic order, and transparent attribution. *Nothing invented*: a dark node with neither supported parents nor a residual is reported unsupported and stays at its transported prior.

When the target *is* observed, the residual measurement is

$$
e_i=d_i-\textstyle\sum_j (p_{ij}/q_i)\beta_{ij} m_j,
\tag{11}
$$

the dislocation of the print against the contemporaneous systematic prediction — $10-13=-3$ in the story — and the state updates either *hard* (certified prints keep their full dislocation: $m_u^+=e$, the diffuse-prior limit) or by a finite-quality Kalman step with gain $K=V_u^-/(V_u^-+V_{\mathrm{obs}}+\beta^2V_j+1/p)$. One numerical lesson from building it is worth recording: the posterior variance must be computed as $K\,r$ (gain times measurement variance), *not* as the algebraically equal $(1-K)V^-$ — in the diffuse limit $V^-\to\infty$ the latter is $\infty\cdot0$ in floating point and cancels catastrophically; the golden suite caught it. Either way the update is cut at the source, and the standardized conflict

$$
\chi_i=\frac{d_i-m^D_i}{\sqrt{V_{\mathrm{obs},i}+V^D_i}}
\tag{12}
$$

is surfaced prominently (Figure 10B): a loud $|\chi|$ means a genuine idiosyncratic shock, a bad quote, a broken beta, or a timestamp problem — the model *keeps* the certified observation and raises the flag, rather than letting the surprise contaminate the source.

### 5.3 The harmonic completion

Directed influence is the wrong semantic for some relations. A calendar ladder is not a causal chain — observing a neighbouring expiry legitimately informs the missing one *in either direction* after maturity normalization — and some peer relations are genuinely symmetric. These stay *reciprocal*: they keep exactly the pairwise factor of Definition 1 (the layered mode reuses the message factor, not a lookalike), assembled as $Q_{H}=\sum_e p_e\,u_eu_e^{\mathsf T}$. What changes is the boundary treatment, and here the gauge potentials of "The accountant: the information-form posterior" earn their second life. When the betas are cycle-consistent, $\beta_{ij}=g_i/g_j$, the change of variables $z_i=g_iy_i$ turns every factor into $p_e g_i^2(y_i-y_j)^2$: the beta-relation problem *is* an ordinary weighted harmonic problem in $y$. For calendar betas $g_i=T_i^{-\alpha_T}$, so at the locked $\alpha_T=1$ the graph harmonically extends $T\,z$ — the total-variance-injection reading of equation (4), now as a Dirichlet problem. A fresh certified boundary set $S$ is clamped and the free nodes solve

**Central equation.**

$$
\widehat z_F=-\,Q_{H,FF}^{-1}\,Q_{H,FS}\,d_S,
\qquad
\Omega=P^{-1}+B_S V_S B_S^{\mathsf T},
\tag{13}
$$

the classical weighted graph Dirichlet solve — with one honest refinement: clamping concerns the published *central* value, not the statistical uncertainty. The lit covariance $V_S$ enters every incident factor through $\Omega$, so a finite-quality boundary widens its dependents' bands, and shared boundary uncertainty is *correlated* across the factors it touches — the same one-source-is-one-source accounting as "The accountant: the information-form posterior", now at the boundary (Figure 9A: the 1M node lands at the exact extension $+3.00$ vol points while its band carries the boundary's uncertainty). Directed predictions $(m^D_i,V^D_i)$ enter the same solve as *unary* information — soft anchors at the target, never pairwise edges back to their parents, so the completion can blend a cross-asset prediction with calendar support yet still cannot update the source that produced it. (Predictions that share parents are correlated; the exact joint block from the directed pass's covariance is wired in the solver, with the diagonal form the v1 default — an adjudicated choice, "Evidence and the gates".) A screening anchor $D_\kappa$ may be added, and the ledger's $\kappa$ closes its circle: the same object that made the smooth prior proper and mechanized the message level here shrinks harmonic support toward the prior — and the product is explicit that $\kappa>0$ is a *screened* field, a retention policy, not a harmonic extension.

> **Figure 9 — The boundary policy on the SPX ladder (figure not included in this pack).** The boundary policy on the SPX ladder (production harmonic solver, one $+1$ vol-point print at 3M). A: fresh and certified, the print is a Dirichlet boundary: its own node publishes $d$ exactly, 1M lands at the exact contract extension $+3.00$, and the boundary's own calibration uncertainty widens the dependents through $\Omega$. B: the same print past the clamp age, demoted to a soft unary anchor under a screen: its node no longer sits at $d$ (production: $+0.58$), the print competes with the ladder and the screen, and every band widens. Rigidity is earned by freshness and certification — never granted to a stale mark. *Panel A shows the fresh-certified case: the 3M node clamped at $+1.00$ exactly, the 1M node at the full $\alpha_T=1$ extension $+3.00$ vol points, and the dependents' bands widened by the boundary's own calibration covariance through $\Omega$. Panel B replays the same print past the clamp age: demoted to a soft finite-precision anchor, the 3M node itself settles at $+0.58$ — outvoted partway by the ladder and the screen — and every band in the panel is wider. The takeaway: the same observation earns two different treatments, and the dial between them is a stated age-and-certification policy, not an emergent weight.*

### 5.4 Who is a boundary: the observation classes

The workflow sorts every node, at every solve, into one of four classes, and the sorting is the mode's trading policy. A *fresh certified* calibration — age within the clamp window *and* passing fit quality, coverage and arbitrage certification; freshness alone is not sufficient — is a hard boundary: clamped centrally, uncertainty into $\Omega$. A *carried* observation rides its lease as a causal source state. A *soft stale* observation is too old to clamp but not worthless: it demotes to a finite-precision unary anchor and now *competes* with the parent prediction — a print from this morning outvoted, eventually, by what the index has done since (Figure 9B). An *unobserved* node receives directed predictions, harmonic support, its advanced residual, or nothing but the transported prior. The four classes are the four possible answers to "how much should this node's own history bind today's mark?", and the dial among them is a stated age policy, not an emergent weight.

### 5.5 The decomposition: every mark explains itself

Because the layers are explicit, every dark mark carries an exact additive identity — baseline, plus systematic (what the parents predict), plus residual (the node's own persisted dislocation), plus harmonic correction (what reciprocal support added) — and the wire reports the four parts with their variances. Figure 10A shows it through the production pass on the six-node universe of "One universe, three answers": AAPL, carrying a planted $-0.40$-point residual aged one day under $H=5$, publishes systematic $+0.82$ plus residual $-0.35$ $=+0.47$ vol points, while MSFT — same parents, no dislocation — publishes its systematic alone; the identity is exact by construction, and panel B sweeps the $\chi$ gauge a fresh conflicting print would ring. This is the layered mode's answer to attribution: not a numerical gain decomposition after the fact, but the model's own state variables, printed.

> **Figure 10 — The mark explains itself (figure not included in this pack).** The mark explains itself (production directed pass, six-node universe, AAPL carrying a planted $-0.40$-point residual aged one day at $H=5$). A: the additive identity per name — systematic $s$ from the index and ETF, plus the persisted residual $u$, equals the published $m^D$; MSFT differs from AAPL exactly by the dislocation. B: the residual-surprise gauge of equation (12) for a hypothetical fresh AAPL print: the badge thresholds $|\chi|>1$ (amber) and $|\chi|>2$ (rose) are the desk's tell for a genuine idio shock versus a bad quote — the observation is kept either way; the flag is the product. *Panel A shows the stacked additive identity for the two names: AAPL's published mark is systematic $+0.82$ plus its decayed planted residual $-0.35$, totalling $+0.47$ vol points, while MSFT — identical parents, no dislocation — publishes the systematic $+0.82$ alone; the two names differ by exactly the persisted dislocation. Panel B sweeps a hypothetical fresh AAPL print through the $\chi$ gauge of equation (12), showing where the amber ($|\chi|>1$) and rose ($|\chi|>2$) badges would ring. The takeaway: attribution here is the model's own state variables printed, not a post-hoc numerical decomposition.*

> **Figure 11 — The memory dial, asserted and adjudicated (figure not included in this pack).** The memory dial, asserted and adjudicated. A: the production residual state advancing the story's $-3$-point dislocation under half-lives $H\in\{1,5,20,\infty\}$ — the desk's statement of how long a private dislocation is believed. B: the recorded Campaign-2 verdict (stored, "Evidence and the gates"): full-LOO ATM RMS is *monotone* in $H$ — memoryless 280.2 bps beats $H{=}1$d (285.1) beats $H{=}5$d (290.1) beats $H{=}20$d (305.5) beats never-forget (333.1) — so at the one-day horizon the optimum is $H\to0$: yesterday's dislocation carries more noise than signal on this universe. The assertion the panel-A dial makes is exactly the one the daily tape declines to reward — and exactly the one the intraday replay *did* reward, at an interior optimum $H\approx0.1$ d ("Evidence and the gates"). *Panel A plots the $-3$-point dislocation advanced through the exponential persistence $\phi(\Delta)=2^{-\Delta/H}$ for $H=1$, $5$, $20$ and $\infty$: the shortest half-life forgets within days, the infinite one is the flat staircase of Figure 1A. Panel B is the daily campaign bar chart: full-LOO ATM RMS rising monotonically from 280.2 bps (memoryless) through 285.1 ($H=1$ d), 290.1 ($H=5$ d) and 305.5 ($H=20$ d) to 333.1 (never-forget). The takeaway is two-sided: at daily granularity the optimum is $H\to0$, yet the intraday replay later found the interior optimum $H\approx0.1$ d — the memory dial is real, and its value lives below the day.*

### 5.6 State discipline, and a cautionary case file

Persistence buys the desk path; it costs causality discipline, and the discipline is machinery, not policy prose. The store threads chronologically: a residual is advanced *before* any same-time update; holdout and what-if solves read a pre-dated snapshot and never write (mutating persistent state would leak the scored day back into itself); and the store is stamped with a configuration identity — change the relations that define a residual's meaning and the affected entries are purged rather than silently reinterpreted. Baseline alignment is part of the same discipline: the residual is defined against aligned innovations, so a change in the transported baseline between timestamps must not masquerade as an idiosyncratic move — if a clean common-epoch conversion cannot be constructed, the residual takes wider process variance or is rejected.

> **Case file — the store that purged itself.**
>
> **Setup.** The first adjudication campaign of the layered mode ran four half-life variants over the frozen benchmark regimes — and produced four *byte-identical* result sets, the half-life knob apparently inert.
>
> **Diagnosis.** The benchmark harness re-estimates its cross-relation betas from each day's data, so they drift daily; the store's configuration identity hashed the beta *values*; therefore every day-pair looked like a configuration change and purged the residual store. Residuals never survived a single day: the layered mode ran spatially (its rows differed from the smooth-field arm everywhere) but with zero temporal memory — the safety rule, firing on estimation drift, had silently removed the very thing under test.
>
> **Fix and lesson.** The store identity became caller-owned: the harness pins a stable label per variant, while the structural hash remains the default so an explicit edit still invalidates — both behaviours test-locked. The invalidated campaign was retained as the memoryless-layered ablation arm, which is why Figure 11B can attribute the memory effect specifically. *A cache-invalidation rule wired to estimated parameters will fire on estimation noise; state identity must be owned by whoever defines what "the same configuration" means.*

**Exercise 4.** From equation (9) with $H_B$ finite, show that after the $t=3.5$ update of "A morning's story: the asynchronous pair" the $t=4$ mark is $14-3\cdot2^{-0.5/H_B}\ge11$, with equality as $H_B\to\infty$: mean reversion can only make $B$ catch *up* to $A$ faster — no half-life explains a mark below $11$, which is why the flat staircase identifies a long half-life and why "forget faster" is the only memory dial the data of Figure 11B could ask for.

## 6. One universe, three answers

The three assertions are now side by side on one miniature universe — an SPX calendar ladder (1M/3M/6M), the sector ETF XLK, two technology names; lit: SPX 3M $+1.00$ vol point and XLK 3M $+0.55$ (Figure 12). Every difference in the figure is an assertion, not a tuning. At SPX 1M the layered mode publishes $+3.00$ — the full $\alpha_T{=}1$ contract through the clamped boundary; the learned message level publishes $+0.66$ — the same contract shrunk by the measured calendar transfer; the smooth field publishes $+0.71$ — not a contract at all, but the smoothness compromise between the lit move and the zero anchor. At the dark names the message and layered answers nearly agree (corroborated index-and-ETF transfer) while the smooth field hears the same signals as generic neighbour pressure. None of the three is "the wrong number" — each is the exact consequence of its prior, which is the note's thesis in one picture. But put a trader in front of the figure and ask which column they would initial: only the layered column is, number by number, the direct consequence of sentences the desk actually said — the other two are what a solver concludes when the desk says less.

> **Figure 12 — The thesis figure (figure not included in this pack).** The thesis figure: one universe (SPX ladder + XLK + two names, two lit calibrations), three production solves. Layered desk force extends the full calendar contract to 1M ($+3.00$); the learned message level shrinks the same contract to $+0.66$; the smooth field, asserting no contract, decays the move to $+0.71$. At the dark names the two contract modes agree (corroborated cross transfer) while the smooth field treats the signals as neighbour pressure. Bars carry $\pm1$ posterior sd: the layered 1M band is the boundary's $\Omega$-widened uncertainty, not false confidence. *The figure draws three grouped bars — one per propagation mode — at each node of the six-node universe. At SPX 1M the three answers are $+3.00$ (layered, full clamped contract), $+0.66$ (messages at the learned level) and $+0.71$ (smooth field); at the dark names AAPL and MSFT the generated values are $+0.82$ (layered, desk force), $+0.41$ (messages, learned) and $+0.28$ (smooth field) — the two contract modes near-agreeing through corroborated index-and-ETF transfer while the smooth field reads the same signals as generic neighbour pressure. Every bar carries its $\pm1$ posterior sd, the layered 1M band visibly widened by the boundary's own uncertainty through $\Omega$. The takeaway is the note's thesis: three defensible numbers per node, each the exact consequence of what its prior asserts.*

### 6.1 The desk surface

The mode dial and every object in this note are first-class in the product's Graph workspace, and four screenshots close the loop from mathematics to desk. Figure 13 is the shell after a layered what-if run: a $+1$ vol-point pulse on SPY's 18-month node spreads through its own calendar ladder and across the cross relations to QQQ and AAPL; the top bar carries the observation-source toggle, the three-mode propagation segment with Layered explicitly selected for the what-if (the segment's initial state follows the saved options default, which is precision messages since the 2026-07-27 flip; this capture predates it), the configuration and preflight chips, and the run summary (1 observed, 11 extrapolated); the canvas colours posterior shift and rings observed nodes; the diagnostics drawer is already raising the loud-$\chi$ banner of equation (12). Figure 14 shows the two configuration surfaces: the relationships pane (left) states the calendar policy in desk units — amplitude preset, level $\rho$, shape $\alpha_T$, decay family and its $\epsilon_T$, with a live worked example ("6M informs 3M: $+1.00$ pt → $+2.00$ pt message, relationship uncertainty $2.94$ pt") — and the per-relation editor (right) lists every relation with its class, its *semantics* column (auto · reciprocal versus directed — the "Assert dependencies" split, per row), its precision-rule chip, per-handle betas and the implied-reverse reading of "Why factors, not averages: the dead informer", above a scenario preview locked to this note's golden numbers. Figure 15 is the inspector on a dark AAPL node after the layered run: the decomposition card prints the "The decomposition: every mark explains itself" identity (baseline $20.0\%$, systematic $+0.0$, residual $+0.0$, harmonic $+71.6$ bp — the auto taxonomy is all-reciprocal, so the move rides the harmonic layer), the incoming-messages table lists each relation's $z\cdot\beta$ message with the $\Leftarrow$ implied-reverse row, and the footer states Exercise 3's lesson verbatim: local consensus $+72.1$ bp at conditional confidence $q$, final marginal $+71.6\pm118$ bp — "local $\neq$ final: the marginal folds in informer uncertainty and shared-route covariance — trust the final."

> **Figure 13 — The Graph workspace after a layered what-if run (screenshot not included in this pack).** The Graph workspace after a layered what-if run (live capture). Top bar: observation source, the three-mode segment (Layered active), config and preflight chips, run summary. Canvas: the $+1$ vol-point pulse on SPY 18M spreading through the calendar ladder and the cross relations; observed nodes ringed, posterior shift coloured. Drawer: the diagnostics table with the loud-$\chi$ residual-surprise banner. *This is a live application screenshot of the three-pane Graph shell. The top bar reads left to right: the observation-source toggle, the propagation-mode segmented control with Layered selected for this what-if, the configuration and preflight status chips, and a run summary reporting 1 observed and 11 extrapolated nodes. The central canvas draws the node graph — SPY's calendar ladder plus cross relations to QQQ and AAPL — with the $+1$ vol-point pulse on SPY 18M colouring each node by posterior shift and ringing the observed node. The bottom diagnostics drawer shows the per-node table with a prominently raised loud-$\chi$ residual-surprise banner, equation (12) surfaced as product furniture.*

> **Figure 14 — Configuration in desk units (screenshots not included in this pack).** Configuration in desk units (live captures). Left: the calendar policy card — amplitude preset and level $\rho$, shape $\alpha_T$, decay family with $\epsilon_T$, and a live worked example of the "Assert relations" contract. Right: the per-relation editor — class, the per-row *semantics* column (reciprocal vs directed, the "Assert dependencies" split), precision rule, per-handle betas, and the implied-reverse column of the canonical-orientation identity; the scenario preview at the bottom is locked to this note's golden numbers. *The left capture is the relationships policy card: dropdowns and dials for the amplitude preset, the class level $\rho$, the maturity-shape exponent $\alpha_T$, and the precision decay family with its $\epsilon_T$, closed by a live worked example reading "6M informs 3M: $+1.00$ pt → $+2.00$ pt message, relationship uncertainty $2.94$ pt". The right capture is the per-relation editor table: one row per relation carrying its class chip, a semantics column distinguishing auto-reciprocal rows from directed arcs, the precision-rule chip, the three per-handle betas, and the implied-reverse column computed from the canonical-orientation identity — with the deterministic scenario preview at the bottom pinned to the golden numbers of this note.*

> **Figure 15 — The inspector on a dark name after a layered run (screenshot not included in this pack).** The inspector on a dark name after a layered run (live capture): the decomposition identity of "The decomposition: every mark explains itself" as a card (this auto-taxonomy run is all-reciprocal, so the move rides the harmonic part), the incoming messages with the implied-reverse row, and the local-vs-final distinction of Exercise 3 stated as product copy. *The capture shows the node inspector panel for a dark AAPL node. Its decomposition card prints the four-part identity: baseline $20.0\%$, systematic $+0.0$, residual $+0.0$, harmonic $+71.6$ bp — this auto-taxonomy run is all-reciprocal, so the whole move rides the harmonic layer. Below it, the incoming-messages table lists each relation's $z\cdot\beta$ message in receiver units with a $\Leftarrow$ implied-reverse row per relation. The footer restates Exercise 3 as product copy: local consensus $+72.1$ bp at conditional confidence $q$, final marginal $+71.6\pm118$ bp, with the caption "local $\neq$ final: the marginal folds in informer uncertainty and shared-route covariance — trust the final."*

## 7. Evidence and the gates

The empirical discipline runs in three layers, and this section quotes its records — including the ones that decline to flatter the note's most expressive mode.

**Golden contracts.** Every mean-semantics behaviour of "Assert relations: precision messages" and "Assert dependencies: the layered dynamic-harmonic mode" — full transmission, competition, cross-asset averaging, multi-hop accumulation, the dead informer, the repeated path, shrunk-mode corroboration, baseline-once, the asynchronous A/B path, zero reverse influence, exact target ownership, store invalidation — is a fixture with an expected number, checked against an independent brute-force Gaussian reference and reproduced through the production modules at $10^{-12}$ (the A/B staircase of Figure 1A is replayed against the golden fixture inside this note's own figure generator). The smooth field is locked differently but equally: byte-identity of the wire default and rollback against the full legacy suite.

**The design study.** The empirical levels quoted throughout — transfer slopes 0.391 (index), 0.762 (peer), 0.23 (calendar), the corroboration adjudication of Figure 5, the calendar noise seeds of Figure 6 — come from a stored study over three historical regimes of benchmark rows, read from its artifact, never re-run. The same row bank measured the spine's extrapolation skill (the smooth-field record of "Assert smoothness: the smooth field"), so graph extrapolation as such is not the hypothesis under test in what follows; the marginal value of each *assertion* is.

**Gate one: do contracts beat smoothness?** The message mode's promotion to default was pre-registered: material dark-name skill over both the transported prior and the smooth field, no stressed-regime degradation, no calm harm beyond tolerance, honest bands ($\operatorname{std}\zeta\approx1$, coverage near nominal), no unstable cycles, no wing deterioration — with the recorded expectation that the `desk` preset would lose day-horizon RMS (it is a belief mode and ships regardless; the gate adjudicates the *default*). The campaign's intersected verdict: message-learned full-LOO ATM RMS 280.9 bps against the smooth-field base 279.3 — no material edge, bands running narrow ($\operatorname{std}\zeta$ 2.07 against the base's over-wide 0.74) — so *no default change on this evidence*: the daily gate did not clear, and its failed table stays on the record. The default nonetheless moved, on 2026-07-27, and the basis is the intraday async replay of the next paragraphs, where the two static operators finally separate: the smooth field measures nearly inert on intraday innovations (its zero-innovation anchor at day-scale stiffness shrinks them to almost nothing) while the message carrier reads them at $65.8$ bp with honest bands. The flip is the *options* default only — the wire default, the byte-identity locks and the harness keep the smooth field, which is also the explicit rollback.

**Gate two: does the layered assertion pay?** The layered mode's pre-registered table was adjudicated on 21,958 intersected out-of-sample rows across seven arms, and the verdict is the most instructive record in the project: *record, hold adoption*. Three findings, stated exactly — and in the order a desk should read them. (i) *The layered spatial solve carries the family's only measured edge in the stressed regimes*: against the smooth-field base, warm full-LOO improves by $-14.7$ bps in the August-2024 spike and $-9.2$ in the October-2022 bear — the two regimes where books actually bleed and where every other arm, message mode included, adds nothing. The directed clamp-and-cut helps exactly when systematic moves dominate, which is the mechanism doing what it was designed to do; the price is $+6.2$ bps in the calm regime, when there is little systematic signal for the structure to carry. (ii) *Day-old residual memory does not pay*: full-LOO RMS is monotone in the half-life (Figure 11B) — the memoryless layered arm (280.2) beats every finite $H$ and the never-forget desk arm (333.1) — so at daily granularity the optimum is $H\to0$: yesterday's private dislocation is noise by the next morning. Note the scope of that sentence before generalizing it: the harness can only test dislocations that are a full day old, and the dislocation of "A morning's story: the asynchronous pair" was hours old — the finding prices one dial (memory) at one horizon (daily) on one universe; it does not price the mode, whose spatial half just posted the edge in (i) *with the memory switched off*. (The intraday replay below did later price the spatial half on its ETF triangle, and found it behind the reciprocal message carrier there — a counterweight recorded in the next paragraph, with the reason that universe is the directed cut's worst case.) (iii) *Calibration and wings flag real work*: $\operatorname{std}\zeta$ 1.68 (the diagonal unary anchors understate dark-node variance when predictions share parents — the joint block is wired and first in line), and a wing-RMS regression (193 vs 121 bps on the liquid split) traced to the harness broadcasting vol-normalized ATM betas to the shape handles — partially mitigated since, with full-amplitude shape transfer through directed anchors still an open pass. The decision: the layered mode is a session-level opt-in — deliberately never seeded from saved options — and the daily message-gate *verdict* stands unchanged even though the default has since moved on other evidence ("Evidence and the gates", gate one).

**The decisive experiment, and its recorded verdict.** The daily campaign tests daily granularity, where every held-out node relights every day; the layered mode's target regime — the story of "A morning's story: the asynchronous pair": a name lit once mid-session, marked against a moving liquid source, dislocations living for hours — is precisely what a daily harness cannot see. The pre-registered asynchronous timestamp replay over stored intraday history has now run (an ETF triangle, seven arms over eight sessions, $13{,}356$ scored rows per arm), and its five-gate table is filled. The mode's central mechanism is *validated*: the residual half-life has an *interior* optimum — memoryless $80.6$ bp $\to$ $H\approx0.1$ d at $73.7$ $\to$ never-forget desk at $108.1$ — and the per-bucket memory skill decays $18.1\to10.0\to6.4\to2.5$ bp exactly as the OU prior predicts, with honest bands ($\operatorname{std}\zeta$ $0.80$). The daily harness's monotone "memory never pays" was a horizon artifact, as this note argued it would be; carried state *is* worth carrying inside the session, and the desk's never-forget instinct is measurably wrong at both horizons — the dial matters. One gate failed, and it is the finding that sets the follow-up: the plain message carrier read the same sessions at $65.8$ bp, beating every layered arm — on that universe the bottleneck is the *spatial* carrier, not the memory (the directed cut discards target→hub information that reciprocal pooling keeps, and three near-exchangeable ETFs punish directedness by construction), and the residual's value lives inside the session, gone by the next day. The pre-registered decision rule was applied verbatim: *record, hold adoption* — the layered mode stays opt-in, and the recorded follow-up is the NAMES campaign (a hub with genuinely asymmetric single names, where a name cannot inform the index and the cut should finally earn its cost). But the reader should be clear about what did *not* wait on that experiment. Direction, rigidity and the decomposition are not hypotheses under test — they are audit requirements, and no RMS result can substitute for them: a solver that lets a satellite print mark down the index is not a slightly less accurate solver, it is a wrong one, whatever its score. On those requirements the layered mode is not the leading candidate — it is the only candidate; the replay has now said how hard to lean on the memory (hard within the session, not across the night), the NAMES campaign will say where direction pays, and neither was ever going to decide whether the desk needs its language.

## 8. What is genuinely original here

Gaussian fields, factor graphs and state-space models are classical; the synthesis is specific. *The assertion dial as an architecture*: three priors of strictly increasing structure behind one seam, so the desk chooses what to claim, not which product to buy — and the modes are honest about being different questions, not rival answers to one. *Contractual propagation for volatility*: every desk-facing behaviour a golden-locked theorem, amplitude split into locked shape and measured level, the level mechanized by a node-linked anchor validated on stored rows to 0.3% with zero free parameters. *The dead-informer analysis*: a joint-distribution defect invisible to every local conditional, surfaced and used to select the factor form. *A trading-native state layer*: influence arcs cut at the source, residual memory with an asserted half-life, boundary rigidity earned by certification — with the causal replay itself a golden acceptance test. *Honesty rules as first-class machinery*: improper components left improper, baseline uncertainty placed exactly once, attribution by source, marks that print their own decomposition. And *evidence discipline*: pre-registered gates, expectations recorded before sweeps, negative findings (memory at the day horizon; the message RMS tie; the layered spatial deficit on the intraday triangle) published in the same breath as the wins — a failed daily gate kept verbatim while the default moved on other recorded evidence, an adoption held even as the mechanism validated — with the store-purge case file kept as a lesson rather than buried.

## 9. Limitations

Where the guarantees stop, per mode and shared. *The layered adjudication is now two-horizon, and neither horizon sells on RMS*: the daily verdict recorded the stressed-regime spatial edge and priced day-old memory at zero; the intraday replay validated the memory mechanism ($H\approx0.1$ d, in-session) but measured the directed spatial carrier behind the reciprocal message operator on its exchangeable-ETF universe — so the mode's case rests on its stressed-regime daily edge, its audit semantics, and the NAMES campaign not yet run (all three on the record above). *Correlated informers and parents*: the message $q_i$ adds configured precisions as if conditionally independent, and the layered v1 unary anchors are diagonal — both overstate joint confidence when sources share a factor (the recorded $\operatorname{std}\zeta$ 1.68); the exact joint block exists in the solver and its adjudication is first in line. *Shape transfer through directed anchors is unfinished*: broadcasting vol-normalized ATM amplitudes to skew and curvature caused the recorded wing regression; the harness now pins unit shape betas, and a measured shape amplitude (or zero cross shape transfer) is an open pass. *Cross-class precision seeds are upper bounds* (ticker-median measurement). *The amplitude shape is weakly identified at the day horizon* — $\alpha_T=1$ is held by semantics, not by $R^2$. *Hybrid mode is machinery, not a recommendation* (validated only at its zero-weight identity with pure messages). *The solves are dense*, sized for the $O(10^2$–$10^3)$-node selected universe; the factor lists and the DAG pass are sparse-ready. *Residual state requires common-epoch alignment*: baseline transport between timestamps can masquerade as an idiosyncratic move, and the discipline is wider variance or rejection, never silent trust. *Calendar arbitrage remains soft* in all three modes: propagation moves maturity signals but imposes no hard cross-expiry projection — publish-time diagnostics and the projection of Note 09 remain the fence. And *curvature stays the weakest handle* end to end, in identification and in units.

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

*Table 2 — Propagation-mode hyperparameters.*

| Knob | Default | Role |
|---|---|---|
| `propagationMode` (wire) | `smooth_field` | The dial on a bare solve request: `smooth_field` / `precision_messages` / `hybrid` (config-only) / `layered_dynamic_harmonic`. Kept at the smooth field so replay, the byte-identity locks and the harness are untouched; the layered value is a session-level opt-in — saved options never seed it. |
| `graphPropagationMode` (options) | `precision_messages` | What the application seeds and a desk runs; flipped 2026-07-27 on the intraday separation with the failed daily gate on the record ("Evidence and the gates"). A store that ever saved options keeps its explicit value until re-saved. |

*Smooth field ("Assert smoothness: the smooth field"):*

| Knob | Default | Role |
|---|---|---|
| $\eta$, $\kappa$ | autotuned | Directed-smoothness weight (reach); local-smallness anchor. Seeded from saved options; the autotune is the *production leave-one-out* harness over a seven-point $\eta$ grid on calibrated hold-outs (the old sandbox tuner is deleted), with descriptive refusals on non-field modes, active what-if pulses, or too few candidates. |
| $\lambda$, $\nu$ | $0$, $0.1$ | Optimal-transport tangent term (off by default) and its source allowance. |
| edge weights / $\beta$ overrides | auto-lattice | Raw trust weights and per-edge amplitude overrides on the calendar/cross lattice. |

*Messages ("Assert relations: precision messages"):*

| Knob | Default | Role |
|---|---|---|
| `calendarBetaExponent` | $1.0$ (per handle) | The amplitude shape $\alpha_T$ of equation (4). |
| `calendarAmplitude` / `crossAmplitude` | $1.0$ | Class levels $\rho$; presets desk $=1.0$ / learned $\approx0.23$ calendar, $\approx0.39$ index ($\alpha_T{=}1$ values). |
| `calendarPrecisionScale` $p_0$, `Epsilon` $\epsilon_T$, `Decay` | $1.7{\times}10^3$, $0.97$, inv-$\sqrt{\text{gap}}$ | The confidence family of equation (6); constant and log-distance ablations ship beside it. |
| `crossPrecisionScale` | $1.3\times10^4$ | Constant cross-relation precision (index seed; upper bound). |
| `innovationAnchorPrecision` | derived | Override for equation (5); unset $=$ node-linked from $\rho$; $\rho=1$ gives $\kappa=0$ exactly. |
| `cycleBetaTolerance` | $10^{-9}$ | Gauge-sweep flag threshold. |
| `messageEdges` / persisted rules | — | Request relations → persisted schema rules → auto relations, in that precedence; draft and active configurations are versioned with an event log. |

*Layered ("Assert dependencies: the layered dynamic-harmonic mode"):*

| Knob | Default | Role |
|---|---|---|
| `relationSemantics` | class default | Per-row `reciprocal_harmonic` / `directed_state`; defaults: calendar, sector peer, custom → reciprocal; broad index, sector ETF → directed. Auto relations are always reciprocal — a directed arc is an explicit configuration. Directed cycles are rejected. |
| `clampMaxAgeDays` | $1$ | The freshness window for hard Dirichlet boundaries; older certified observations demote to soft unary anchors ("Who is a boundary: the observation classes"). |
| `residualHalfLife` | never (RW) | The memory dial $H$ of equation (9); per-handle broadcastable. |
| `residualConfigVersion` | structural hash | The store identity: caller-owned stable label, else a structural hash of the relations — changed identity purges affected residuals ("State discipline, and a cautionary case file"). |
| residual store | persisted | Restored at startup, written only by real layered solves on certified target observations; what-if and holdout solves never write. |
| screen $\kappa$ | $0$ | Screened-harmonic retention toward the prior ("The harmonic completion"); $\kappa>0$ is a stated policy, not an extension. |

*Hidden (module constants):*

| Knob | Default | Role |
|---|---|---|
| `HANDLE_PRECISION_SCALE` | $(1,0.36,0.0036)$ | Per-handle precision units ("Amplitude: shape locked, level measured"). |
| `RELATION_CLASSES` | 5 classes | calendar / broad_index / sector_etf / sector_peer / custom. |
| `DISCONNECTED_Z_SD` | $(0.03,0.05,0.5)$ | The honest no-active-path innovation sd per handle (one typical move). |
| canonical orientation | shorter $T$ | Auto calendar receiver; reverse identity $p_{j\leftarrow i}=p_{i\leftarrow j}\beta^2$. |

## Appendix B. Performance notes

1. **All three solves are dense at the current design point** ($O(10^2$–$10^3)$ nodes) and sparse-ready beyond it: the message factor list is $O(E)$ triplets with no normalization coupling; the layered directed pass is $O(E_D)$ per handle in topological order; the harmonic completion inverts per factor-support component, so one disconnected block never pays for another and the Cholesky guard localizes any conditioning failure to a named component.
2. **The smooth field solves in covariance form** because $n_{\mathrm{obs}}\ll N$: only the observed columns and one $m\times m$ solve, marginals by a single contraction — no dense posterior matrix is formed; the same stored columns price the observation-selection question (which dark node is worth quoting next) in closed form.
3. **The mode fork adds no data work**: universe, transported priors, innovations and calibration precisions are computed once, upstream of the fork; the layered mode adds only the residual-store read/advance and its persistence write-back.
4. **Adjudication runs where long jobs survive**: the campaigns execute from the user's own shell (chunked, resumable parts beside the frozen fixtures); tool-spawned background jobs are killed on this box — a recorded operational constraint.
5. No benchmark in this note was re-timed; figures and golden numbers were generated at commit `e2e6c9a` on 2026-07-24 through the production modules, and every campaign or design-study number is read from its stored artifact. The two adjudication verdicts and the default flip quoted in "Evidence and the gates" are current as of 2026-07-27, from the findings records anchored in the traceability table.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

*Table 3 — Claims in this note and the code/tests that lock them.*

| Claim | Object | Code anchor | Test anchor |
|---|---|---|---|
| Smooth-field prior, kernel/stationary mass, covariance update, marginal honesty, byte-locked default | equation (1), section "Assert smoothness: the smooth field" | `volfit/graph/build.py`, `volfit/graph/operators.py`, `volfit/graph/prior.py`, `volfit/graph/posterior.py` | `test_graph_example.py`, legacy suite byte-identity |
| Pairwise operator PSD; receiver conditional; canonical orientation; $q_i$ unit mapping | equation (2), Proposition 1 | `volfit/graph/message.py` | `test_graph_message.py` |
| Golden message contracts (transmission, competition, multi-hop, dead informer, repeated path, corroboration, baseline-once) | section "Assert relations: precision messages" | `tests/fixtures/graph_message_golden.json` | `test_graph_message_golden.py` (brute-force reference) |
| Information-form component solve; no-lit honesty; reachability guard; exact attribution | equation (7) | `volfit/graph/message_posterior.py` | `test_graph_message_posterior.py` |
| Residual state, dynamics, leases, hard/Kalman updates, causal ordering, store round-trips | section "State: the residual and the lease" | `volfit/graph/temporal_state.py` | `test_graph_temporal_state.py` (A/B exit gate) |
| Directed pass: exact parent covariance, cut at source, DAG rejection, attribution, $\chi$ | equations (10)–(12) | `volfit/graph/directed_state.py` | `test_graph_directed_state.py` |
| Harmonic completion: Dirichlet partition, $\Omega$, unary anchors (diag + joint), screen, gauge strictness | equation (13) | `volfit/graph/harmonic_posterior.py` | `test_graph_harmonic_posterior.py` |
| Layered orchestration: semantics defaults, boundary policy, store persistence + invalidation, what-if/holdout read-only | sections "Who is a boundary: the observation classes", "State discipline, and a cautionary case file" | `volfit/api/graph_dynamic.py` | `test_graph_dynamic_production.py`, `test_graph_dynamic_golden.py` |
| Mode fork, auto relations, $r^d$ harmonic, band placement, hybrid zero-weight identity, editor/scenario preview locks | section "One universe, three answers" | `volfit/api/graph_message.py`, `api/graph_extrapolation.py` | `test_graph_message_production.py`, frontend vitest locks |
| Campaign records (message gate + the 2026-07-27 flip; layered §16.3 table; intraday adjudication; store-purge post mortem) | section "Evidence and the gates" | `backtest/FINDINGS_message_phase4.md`, `backtest/FINDINGS_dynamic_phase5.md`, `backtest/FINDINGS_dynamic_intraday.md`, `backtest/graph_intraday.py` | stored parts under `backtest/results/benchmark/`; `test_graph_intraday_replay.py` |
| Design study (anchor choice, seeds, learned levels) | section "Amplitude: shape locked, level measured" | `backtest/message_phase0.py` | artifact `results/message_phase0.json` (regenerable) |

## Appendix D. Reference implementation

Each mode's core is a few lines, executed against the production modules before this note was built. The message listing (operator, anchors, information-form solve) agrees with production to $2.3\times10^{-13}$ on a four-node directed universe, and the gauge sweep cross-check flags nothing on a consistent triangle (0 flags) while reporting the planted inconsistent product 0.833. The layered listing (directed means and variances by hand on a three-node chain, plus the Dirichlet extension $-Q_{H,FF}^{-1}Q_{H,FS}d_S$ assembled from raw factors) agrees to $1.0\times10^{-17}$. The smooth listing (stationary mass and the $\beta$-weighted directed residual) agrees to $1.0\times10^{-17}$.

Per the transfer policy of this pack, the reference listing is replaced by exact algorithm specifications. Each was verified against the production package `volfit.graph` (a capability anchor, not a file to reproduce), with the agreements stated above.

**Algorithm 1 — the pairwise message operator.**

*Inputs:* the node count $n$; a factor list of quadruples $(i, j, p, \beta)$ — receiver index, informer index, relation precision, amplitude.

*Output:* the $n\times n$ operator $Q_{\mathrm{msg}}$.

1. Initialize $Q$ as the $n\times n$ zero matrix.
2. For each factor $(i,j,p,\beta)$ in list order: form the vector $u\in\mathbb R^n$ with $u_i=1$, $u_j=-\beta$, zeros elsewhere; add the rank-one term $p\,uu^{\mathsf T}$ to $Q$.
3. Return $Q$; the result is positive semidefinite for any real $\beta$, and no normalization of any kind is applied. The posterior is then assembled as $Q+\operatorname{diag}(\kappa)+H^{\mathsf T}RH$ per equation (7).

**Algorithm 2 — the directed prediction for one target (equation (10)).**

*Inputs:* the target's parent list, each parent $j$ carrying its resolved mean $m_j$ and variance $V_j$; the per-parent relation precisions $p_j$ and amplitudes $\beta_j$; the target's advanced residual state $(m_u, V_u)$.

*Outputs:* the systematic prediction mean $m^D$ and variance $V^D$.

1. Compute the conditional precision $q=\sum_j p_j$.
2. Mean: $m^D=\sum_j (p_j/q)\,\beta_j\,m_j+m_u$ — the precision-weighted, amplitude-mapped parent average plus the residual mean.
3. Variance: $V^D=\sum_j \big((p_j/q)\,\beta_j\big)^2 V_j+V_u+1/q$; in the full production form the first term is replaced by the quadratic form $a^{\mathsf T}\Sigma_{P}a$ with $a_j=(p_j/q)\beta_j$ and $\Sigma_P$ the exact parent covariance carried by the root-variable bookkeeping — the parent cross-covariance terms are included, never assumed zero.

**Algorithm 3 — the Dirichlet extension (equation (13), zero screen).**

*Inputs:* the reciprocal-factor operator $Q_H$; the index partition into free nodes $F$ and clamped boundary nodes $S$; the boundary innovations $d_S$.

*Output:* the extended free-node innovations $\widehat z_F$.

1. Extract the blocks $Q_{H,FF}$ (free–free) and $Q_{H,FS}$ (free–boundary).
2. Solve the linear system $Q_{H,FF}\,\widehat z_F=-\,Q_{H,FS}\,d_S$ (equivalently $\widehat z_F=-Q_{H,FF}^{-1}Q_{H,FS}d_S$); with a positive screen the block $Q_{H,FF}$ gains $\operatorname{diag}(\kappa_F)$ first.

**Algorithm 4 — the stationary mass of the trust kernel.**

*Inputs:* the row-stochastic $n\times n$ trust kernel $K$.

*Output:* the stationary mass $\pi$ with $\pi^{\mathsf T}K=\pi^{\mathsf T}$ and $\sum_i\pi_i=1$.

1. Form $S=K^{\mathsf T}-I$.
2. Replace the last row of $S$ with a row of ones (imposing the normalization $\sum_i\pi_i=1$).
3. Form the right-hand side as the zero vector with last entry $1$, and solve the linear system $S\,\pi=\mathrm{rhs}$.

*Stated production agreements:* message core $2.3\times10^{-13}$ (four-node directed universe with a node-linked anchor: operator matrix, posterior mean, marginal variances); layered core $1.0\times10^{-17}$ (three-node chain directed means and variances, plus the raw-factor Dirichlet extension); smooth core $1.0\times10^{-17}$ (stationary mass and $\beta$-weighted directed residual). The gauge cross-check plants a consistent triangle (0 flags) and an inconsistent one flagged at cycle product 0.833.

## References

1. [RasmussenWilliams2006] C. Rasmussen and C. Williams. *Gaussian Processes for Machine Learning*. MIT Press, 2006.
2. [Koller2009] D. Koller and N. Friedman. *Probabilistic Graphical Models*. MIT Press, 2009.
3. [Pearl1988] J. Pearl. *Probabilistic Reasoning in Intelligent Systems*. Morgan Kaufmann, 1988.
4. [AndersonMoore1979] B. D. O. Anderson and J. B. Moore. *Optimal Filtering*. Prentice-Hall, 1979.
5. [Chizat2018] L. Chizat, G. Peyré, B. Schmitzer and F.-X. Vialard. Unbalanced optimal transport: dynamic and Kantorovich formulations. *J. Funct. Anal.*, 274(11):3090–3123, 2018.
6. [Peyre2019] G. Peyré and M. Cuturi. Computational optimal transport. *Found. Trends Mach. Learn.*, 11(5–6):355–607, 2019.



