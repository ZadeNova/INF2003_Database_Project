"""Import-fixed Bayesian prior shared by seller creation and review writes."""
from decimal import Decimal, localcontext

from bson import Decimal128


def constants(stats):
    stats = stats or {"m": Decimal128("0"), "C": Decimal128("1")}
    return stats["m"], stats["C"]


def bayesian_score(stats, total=0, count=0):
    m, prior = (value.to_decimal() for value in constants(stats))
    with localcontext() as context:
        context.prec = 28  # Match the reproducible import's Decimal context exactly.
        denominator = prior + count
        return Decimal128((prior * m + total) / denominator if denominator else Decimal(0))


def empty_summary(stats):
    return {"count": 0, "sum": 0, "average": Decimal128("0"),
            "distribution": {str(score): 0 for score in range(1, 6)},
            "bayesian": bayesian_score(stats)}


def decimal28(expression):
    """MongoDB Decimal128 arithmetic rounded like the import's 28 significant digits."""
    rounded = {"$round": ["$$value", {"$toInt": {"$subtract": [27,
        {"$floor": {"$log10": {"$abs": "$$value"}}}]}}]}
    return {"$let": {"vars": {"value": expression}, "in": {"$cond": [
        {"$eq": ["$$value", 0]}, Decimal128("0"),
        {"$cond": [{"$eq": ["$$value", rounded]}, "$$value", rounded]},
    ]}}}


def summary_pipeline(stats, before, after):
    """Change only the running totals; derive decimal averages in the same transaction."""
    old = before if before and not before.get("taken_down", False) else None
    new = after if after and not after.get("taken_down", False) else None
    m, prior = constants(stats)
    changes = {
        "rating_summary.count": {"$add": ["$rating_summary.count", int(new is not None) - int(old is not None)]},
        "rating_summary.sum": {"$add": ["$rating_summary.sum", (new or {}).get("score", 0) - (old or {}).get("score", 0)]},
    }
    for score in range(1, 6):
        path = f"rating_summary.distribution.{score}"
        changes[path] = {"$add": ["$" + path, int(bool(new and new["score"] == score)) - int(bool(old and old["score"] == score))]}
    denominator = {"$add": [prior, "$rating_summary.count"]}
    return [{"$set": changes}, {"$set": {
        "rating_summary.average": {"$cond": [{"$gt": ["$rating_summary.count", 0]},
            decimal28({"$divide": [{"$toDecimal": "$rating_summary.sum"}, "$rating_summary.count"]}), Decimal128("0")]},
        "rating_summary.bayesian": {"$cond": [{"$gt": [denominator, 0]},
            decimal28({"$divide": [decimal28({"$add": [decimal28({"$multiply": [prior, m]}), "$rating_summary.sum"]}), denominator]}), Decimal128("0")]},
    }}]
