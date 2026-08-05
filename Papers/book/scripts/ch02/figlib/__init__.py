"""Figure-pipeline library for the standalone LQD paper.

Modules:
    figstyle  -- shared Matplotlib style (serif, restrained palette, PDF export)
    macros    -- the \\Mac<CamelCaseSlug> macro store (paper_macros.tex + MACROS.md)
    data      -- frozen-snapshot access; slices are REBUILT from stored params
    synth     -- synthetic constructions (constant-speed toy, modes, double-hump)
    fig_*     -- one module per figure family (core, market, tails, synth,
                 audit, calendar)
    audit     -- macro-only blocks: certification battery, timing, worked ticket
"""
