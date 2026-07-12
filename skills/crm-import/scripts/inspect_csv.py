#!/usr/bin/env python3
"""
inspect_csv.py — cheaply PROFILE a CSV so the model can propose a column mapping without
reading the whole file into tokens. Deterministic, stdlib-only.

It sniffs the delimiter, counts rows, and for each column reports its fill rate and a few
distinct sample values. That's all the model needs to decide "this column is the email, that
one is the company name" — it never has to see all N rows.

Usage:
    python3 inspect_csv.py contacts.csv
    python3 inspect_csv.py contacts.csv --samples 4

Output (JSON on stdout):
{
  "file": "contacts.csv",
  "delimiter": ",",
  "row_count": 142,
  "columns": [
    {"name": "Full Name", "index": 0, "fill_rate": 1.0, "samples": ["Priya Nair", ...]},
    ...
  ]
}
"""

import csv
import io
import json
import sys


def sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        # Fall back to the most common delimiter present in the header line.
        head = sample.splitlines()[0] if sample else ""
        return max(",;\t|", key=lambda d: head.count(d)) if head else ","


def inspect(path: str, n_samples: int = 3) -> dict:
    # utf-8-sig transparently strips a BOM if present (common in Excel exports).
    with open(path, encoding="utf-8-sig", newline="") as f:
        raw = f.read()

    delimiter = sniff_delimiter(raw[:8192])
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)

    try:
        header = next(reader)
    except StopIteration:
        return {"file": path, "delimiter": delimiter, "row_count": 0, "columns": []}

    fill = [0] * len(header)
    samples: list[list[str]] = [[] for _ in header]
    seen: list[set] = [set() for _ in header]
    row_count = 0

    for row in reader:
        if not any(cell.strip() for cell in row):
            continue  # skip fully blank rows
        row_count += 1
        for i in range(len(header)):
            val = row[i].strip() if i < len(row) else ""
            if val:
                fill[i] += 1
                if len(samples[i]) < n_samples and val not in seen[i]:
                    samples[i].append(val)
                    seen[i].add(val)

    columns = [
        {
            "name": name,
            "index": i,
            "fill_rate": round(fill[i] / row_count, 3) if row_count else 0.0,
            "samples": samples[i],
        }
        for i, name in enumerate(header)
    ]
    return {"file": path, "delimiter": delimiter, "row_count": row_count, "columns": columns}


def main() -> None:
    args = [a for a in sys.argv[1:]]
    n_samples = 3
    if "--samples" in args:
        idx = args.index("--samples")
        n_samples = int(args[idx + 1])
        del args[idx : idx + 2]
    if not args:
        sys.exit("usage: inspect_csv.py <file.csv> [--samples N]")
    print(json.dumps(inspect(args[0], n_samples), indent=2))


if __name__ == "__main__":
    main()
