"""One committed output contract for exact values from the oracle and both engines."""

import csv
import io
import json
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("golden") / "schema.json"


def canonical(output, rows):
    schema = json.loads(SCHEMA_PATH.read_text())[output.split("_")[0]]
    result = []
    for row in rows:
        values = []
        for name, kind in schema["columns"].items():
            value = row.get(name)
            if hasattr(value, "to_decimal"):
                value = value.to_decimal()
            if value is None:
                value = ""
            elif kind.startswith("decimal:"):
                if isinstance(value, float):
                    raise ValueError("Floating-point decimal result refused")
                with localcontext() as ctx:
                    ctx.prec = 50
                    value = format(
                        Decimal(value).quantize(Decimal(1).scaleb(-int(kind.split(":")[1])), rounding=ROUND_HALF_EVEN),
                        "f",
                    )
            elif kind == "bool":
                value = "true" if value else "false"
            elif isinstance(value, (date, datetime)):
                value = value.isoformat()[:10]
            else:
                value = str(value)
            values.append(value)
        result.append(tuple(values))
    columns = list(schema["columns"])
    positions = [(columns.index(key), schema["columns"][key]) for key in schema["sort"]]
    result.sort(key=lambda row: tuple(int(row[i]) if kind == "int" else row[i] for i, kind in positions))
    return result


def csv_bytes(output, rows):
    schema = json.loads(SCHEMA_PATH.read_text())[output.split("_")[0]]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(schema["columns"])
    writer.writerows(canonical(output, rows))
    return stream.getvalue().encode()
