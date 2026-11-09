"""Which B2 variants form the headline comparison (amendment m, docs/plans/benchmark.md). Fixed before any run.

For every output and layer the pair is (PostgreSQL variant, MongoDB variant). The "live" layer compares each engine's
idiomatic computation from the source data; the "maintained" layer compares each engine's maintained summary. Both
engines' variants return only the golden columns. Variants not named here (the originals as first implemented and the
application's own queries) are reported in their own table and never headline a layer. B2c has no maintained summary on
either engine, so it has only the live layer; its PostgreSQL query already returns only the golden columns.
"""

HEADLINE = {
    "B2a": {"live": ("idiomatic", "idiomatic"), "maintained": ("summary", "summary")},
    "B2b": {"live": ("idiomatic", "idiomatic"), "maintained": ("summary", "summary")},
    "B2c": {"live": ("live", "idiomatic")},
    "B2d": {"live": ("idiomatic", "idiomatic"), "maintained": ("summary", "summary")},
}

# The cost of keeping each maintained summary current, one pair per summary: (PostgreSQL variant, MongoDB variant).
REFRESH = {"daily product sales": ("refresh", "refresh"), "delivery scores": ("refresh_scores", "refresh_scores")}


def registered():
    """{(output, engine, variant): (layer, PostgreSQL variant of that layer)} for every variant that belongs to a pair."""
    result = {}
    for output, layers in HEADLINE.items():
        for layer, (postgres, mongo) in layers.items():
            result[(output, "postgres", postgres)] = (layer, postgres)
            result[(output, "mongo", mongo)] = (layer, postgres)
    for name, (postgres, mongo) in REFRESH.items():
        result[("B2refresh", "postgres", postgres)] = ("refresh: " + name, postgres)
        result[("B2refresh", "mongo", mongo)] = ("refresh: " + name, postgres)
    return result
