"""Time the dashboard's history blocks computed from the source and from the maintained summaries, and compare them.

Run it against the stack that holds the data you want to time (nothing but derived summaries is written, by the refresh
at the end). The two paths alternate within each round, so drift on the machine falls on both:

    docker compose exec -T web python manage.py shell < scripts/time_dashboard_history.py

It prints, for the delivery analysis alone and for the whole set of history blocks, the median, minimum and maximum of
every round for each path and their ratio, whether the two paths returned identical results, and the duration of a full
"Refresh sales history". Figures belong in a report only as the output of this script, with the machine they came from.
"""

import statistics
import time

from config import mongo
from dashboard import services

ROUNDS = 7


def milliseconds(function):
    started = time.perf_counter()
    result = function()
    return (time.perf_counter() - started) * 1000, result


def summarise(values):
    return f"median {statistics.median(values):7.1f}   min {min(values):7.1f}   max {max(values):7.1f}"


as_of = services.as_of_date()
summaries_off = lambda as_of, database: None  # noqa: E731 - makes `summary_inputs` untrusted, so the source is used
real_summary_inputs = services.summary_inputs


def with_summaries(function):
    services.summary_inputs = real_summary_inputs
    return milliseconds(function)


def from_source(function):
    services.summary_inputs = summaries_off
    try:
        return milliseconds(function)
    finally:
        services.summary_inputs = real_summary_inputs


with mongo.client() as client:
    database = client[mongo.database_name()]
    cases = {
        "delivery analysis": lambda: services.delivery_analysis(as_of, database),
        "all history blocks": lambda: services.history_blocks(as_of),
    }
    print(f"reporting date {as_of}; {ROUNDS} rounds, source and summaries alternating\n")
    for name, function in cases.items():
        function()  # one untimed run each way warms caches that both paths share
        from_source(function)
        source, summary = [], []
        results = {}
        for _ in range(ROUNDS):
            elapsed, results["source"] = from_source(function)
            source.append(elapsed)
            elapsed, results["summaries"] = with_summaries(function)
            summary.append(elapsed)
        print(f"{name}")
        print(f"  from the source     ms: {summarise(source)}")
        print(f"  from the summaries  ms: {summarise(summary)}")
        print(f"  ratio of medians: {statistics.median(source) / statistics.median(summary):.2f}x")
        print(f"  identical results: {results['source'] == results['summaries']}\n")

refreshes = [milliseconds(services.refresh_sales)[0] for _ in range(3)]
print(f"Refresh sales history (both views and the MongoDB summary), three runs ms: {summarise(refreshes)}")
