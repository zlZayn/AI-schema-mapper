"""Track API token usage and cost per call."""

# DeepSeek pricing (yuan per 1M tokens)
PRICING = {
    "input": 1.0,
    "output": 2.0,
}

_records: list[dict] = []


def reset():
    """Clear all recorded API calls."""
    _records.clear()


def record(name: str, prompt_tokens: int, completion_tokens: int):
    """Record one API call's token usage."""
    cost = (
        prompt_tokens * PRICING["input"] + completion_tokens * PRICING["output"]
    ) / 1_000_000
    _records.append(
        {
            "name": name,
            "tokens": prompt_tokens + completion_tokens,
            "cost": cost,
        }
    )


def summary() -> str:
    """Return a formatted cost summary table."""
    if not _records:
        return "  (no API calls)"

    def pad(s, width):
        extra = sum(1 for c in s if ord(c) > 127)
        return s + " " * (width - len(s) - extra)

    lines = []
    hdr = f"  {'name':<16s} {'tokens':>10s} {'cost':>10s}"
    lines.append(hdr)
    lines.append(f"  {'-' * 16} {'-' * 10} {'-' * 10}")

    total_tokens = 0
    total_cost = 0.0
    for r in _records:
        lines.append(f"  {r['name']:<16s} {r['tokens']:>10d} {r['cost']:>10.6f}")
        total_tokens += r["tokens"]
        total_cost += r["cost"]

    lines.append(f"  {'-' * 16} {'-' * 10} {'-' * 10}")
    lines.append(f"  {'total':<16s} {total_tokens:>10d} {total_cost:>10.6f}")
    return "\n".join(lines)


def total_cost() -> float:
    return sum(r["cost"] for r in _records)
