"""Which B2 variants form the headline comparison (amendment m, docs/plans/benchmark.md). Fixed before any run.

For every output and layer the pair is (PostgreSQL variant, MongoDB variant). The "live" layer compares each engine's
idiomatic computation from the source data; the "maintained" layer compares each engine's maintained summary. Variants
not named here (the originals as first implemented) are reported in their own table and never headline a layer.
B2c has no maintained summary on either engine, so it has only the live layer.
"""

HEADLINE = {
    "B2a": {"live": ("live", "idiomatic"), "maintained": ("view", "summary")},
    "B2b": {"live": ("idiomatic", "idiomatic"), "maintained": ("summary", "summary")},
    "B2c": {"live": ("live", "idiomatic")},
    "B2d": {"live": ("live", "idiomatic"), "maintained": ("summary", "summary")},
}

# The cost of keeping each maintained summary current, one pair per summary: (PostgreSQL variant, MongoDB variant).
REFRESH = {"daily product sales": ("refresh", "refresh"), "delivery scores": ("refresh_scores", "refresh_scores")}
