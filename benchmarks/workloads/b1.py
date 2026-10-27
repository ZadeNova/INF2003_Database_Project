"""Three idiomatic attribute representations with scalar-only bound values."""
import re

from psycopg.types.json import Jsonb

from benchmarks.query import Query


def validate(predicates):
    for key, operation, value in predicates:
        if not re.fullmatch(r"[a-z][a-z_]*", key) or operation not in {"eq", "gte"} or type(value) not in {str, int, bool}:
            raise ValueError("Attribute predicates require safe keys and scalar values")
        if operation == "gte" and type(value) is not int:
            raise ValueError("Integer range required")


def queries(parameter):
    predicates = parameter["predicates"]
    validate(predicates)
    parts, values = [], []
    for key, operation, value in predicates:
        column = {str: "value_text", int: "value_int", bool: "value_bool"}[type(value)]
        operator = "=" if operation == "eq" else ">="
        parts.append(f"EXISTS (SELECT 1 FROM bench_attribute_eav a WHERE a.product_id=p.id AND a.key=%s AND a.{column} {operator} %s)")
        values.extend((key, value))
    output = "B1_" + parameter["name"]
    eav = Query(output, "postgres", "eav", "SELECT p.id AS product_id FROM catalogue_product p WHERE " + " AND ".join(parts) + " ORDER BY p.id", values, golden=output)
    equal = {key: value for key, operation, value in predicates if operation == "eq"}
    parts, values = [], []
    if equal:
        parts.append("attributes @> %s")
        values.append(Jsonb(equal))
    for key, operation, value in predicates:
        if operation == "gte":
            parts.append("(attributes ->> %s)::bigint >= %s")
            values.extend((key, value))
    jsonb = Query(output, "postgres", "jsonb", "SELECT product_id FROM bench_attribute_jsonb WHERE " + " AND ".join(parts) + " ORDER BY product_id", values, golden=output)
    match = {"attributes." + key: value if operation == "eq" else {"$gte": value} for key, operation, value in predicates}
    mongo = Query(output, "mongo", "documents", pipeline=[{"$match": match}, {"$sort": {"_id": 1}}, {"$project": {"_id": 0, "product_id": "$_id"}}], golden=output)
    return [eav, jsonb, mongo]
