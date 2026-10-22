"""PostgreSQL chooses purchasable candidates; one MongoDB facet counts only those candidates."""
from decimal import Decimal
import math

from bson import Decimal128
from django.db.models import BooleanField, FloatField
from django.db.models.expressions import RawSQL
from django.core.paginator import Paginator

from .models import Product, PurchasableProduct

PAGE_SIZE = 24
# The plan bounds a category at about 2k buyable products (the largest has 1,292). A broad name-only search
# keeps only its closest matches, so it never sends tens of thousands of ids from PostgreSQL to MongoDB.
MAX_CANDIDATES = 2000


def visible_products():
    return Product.objects.filter(pk__in=PurchasableProduct.objects.values("id")).select_related("category", "seller")


def candidates(cleaned):
    products = visible_products()
    if cleaned.get("category"):
        products = products.filter(category=cleaned["category"])
    for key, lookup in (("min_price", "price__gte"), ("max_price", "price__lte")):
        if cleaned.get(key) is not None:
            products = products.filter(**{lookup: cleaned[key]})
    query = cleaned.get("q", "").strip()
    if query:
        # Both the trigram similarity operator and literal substring search can use product_name_trgm.
        # Escape LIKE metacharacters separately from SQL binding: they are product-name text, not wildcards.
        escaped = query.replace(chr(92), chr(92) * 2).replace("%", chr(92) + "%").replace("_", chr(92) + "_")
        products = products.filter(RawSQL(
            '("catalogue_product"."name" %% %s OR "catalogue_product"."name" ILIKE %s)',
            [query, "%" + escaped + "%"], output_field=BooleanField()))
        # Closest names first, so a capped candidate list keeps the most relevant products.
        return products.annotate(name_rank=RawSQL('similarity("catalogue_product"."name", %s)', [query],
                                                  output_field=FloatField())).order_by("-name_rank", "-id")
    return products.order_by("-id")


def attribute_definitions(database, category_ids):
    definitions = {}
    for template in database.category_templates.find({"category_id": {"$in": list(category_ids)}}):
        for name, definition in template["attributes"].items():
            previous = definitions.setdefault(name, {**definition, "values": []})
            if previous["type"] != definition["type"]:
                continue
            for value in definition.get("values", []):
                if value not in previous["values"]:
                    previous["values"].append(value)
    return definitions


def facet_match(ids, cleaned, definitions):
    match = {"_id": {"$in": list(ids)}}
    for key, definition in definitions.items():
        value = cleaned.get("attr_" + key)
        if value is not None and value != "":
            match["attributes." + key] = {"$eq": value}
    if cleaned.get("rating"):
        match["rating_summary.average"] = {"$gte": Decimal128(Decimal(cleaned["rating"]))}
        match["rating_summary.count"] = {"$gt": 0}
    return match


def facet_pipeline(ids, cleaned, definitions, page=1):
    results = []
    if cleaned.get("sort") == "top":
        results += [{"$sort": {"rating_summary.bayesian": -1, "_id": -1}},
                    {"$skip": (page - 1) * PAGE_SIZE}, {"$limit": PAGE_SIZE}]
    results += [{"$project": {"_id": 1}}]
    return [
        {"$match": facet_match(ids, cleaned, definitions)},
        {"$facet": {
            "results": results,
            "total": [{"$count": "count"}],
            "ratings": [{"$group": {"_id": {"$cond": [{"$gt": ["$rating_summary.count", 0]},
                            {"$floor": "$rating_summary.average"}, 0]}, "count": {"$sum": 1}}},
                        {"$sort": {"_id": -1}}],
            "attributes": [{"$project": {"pairs": {"$objectToArray": "$attributes"}}},
                           {"$unwind": "$pairs"},
                           {"$group": {"_id": {"name": "$pairs.k", "value": "$pairs.v"},
                                       "count": {"$sum": 1}}}],
        }},
    ]


def matching_products(ids):
    """The explicit, bound cross-store id = ANY path, used for PostgreSQL ordering/pagination."""
    if not ids:
        return visible_products().none()
    return visible_products().filter(RawSQL('"catalogue_product"."id" = ANY(%s)',
                                            [list(ids)], output_field=BooleanField()))


def search_page(database, products, cleaned, definitions, requested):
    ids = list(products.values_list("pk", flat=True)[:MAX_CANDIDATES + 1])
    capped = len(ids) > MAX_CANDIDATES
    ids = ids[:MAX_CANDIDATES]
    try:
        number = max(1, min(int(requested or 1), 2**31))
    except (ValueError, TypeError):
        number = 1
    facets = next(database.product_specs.aggregate(facet_pipeline(ids, cleaned, definitions, number)))
    total = facets["total"][0]["count"] if facets["total"] else 0
    last = max(1, math.ceil(total / PAGE_SIZE))
    if cleaned.get("sort") == "top" and number > last:
        number = last
        facets = next(database.product_specs.aggregate(facet_pipeline(ids, cleaned, definitions, number)))
    matched_ids = [row["_id"] for row in facets["results"]]
    if cleaned.get("sort") == "top":
        page = Paginator(range(total), PAGE_SIZE).get_page(number)
        found = {item.pk: item for item in matching_products(matched_ids)}
        page.object_list = [found[pk] for pk in matched_ids if pk in found]
    else:
        ordering = {"price": ("price", "id"), "price_desc": ("-price", "-id"), "newest": ("-id",)}
        page = Paginator(matching_products(matched_ids).order_by(*ordering[cleaned.get("sort") or "newest"]),
                         PAGE_SIZE).get_page(requested)
    facets["capped"] = capped
    return page, facets


def attach_photos(database, products):
    products = list(products)
    photos = {row["_id"]: row.get("photo_file_id") for row in database.product_specs.find(
        {"_id": {"$in": [item.pk for item in products]}}, {"photo_file_id": 1})}
    for item in products:
        item.photo_file_id = photos.get(item.pk)
    return products
