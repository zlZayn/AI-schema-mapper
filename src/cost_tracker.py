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
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "cost": cost,
        }
    )


def _pad(s: str, width: int) -> str:
    extra = sum(1 for c in s if ord(c) > 127)
    return s + " " * max(0, width - len(s) - extra)


def summary() -> str:
    """Return a formatted cost summary table."""
    lines = []
    hdr = f"  {'name':<16s} {'in':>8s} {'out':>8s} {'cost':>10s}"
    lines.append(hdr)
    lines.append(f"  {'-' * 16} {'-' * 8} {'-' * 8} {'-' * 10}")

    total_prompt = 0
    total_completion = 0
    total_cost_val = 0.0
    if not _records:
        lines.append(f"  {'(no API calls)':<16s} {'0':>8s} {'0':>8s} {'0':>10s}")
    else:
        for r in _records:
            lines.append(
                f"  {_pad(r['name'], 16)} {r['prompt']:>8d} {r['completion']:>8d} {r['cost']:>10.6f}"
            )
            total_prompt += r["prompt"]
            total_completion += r["completion"]
            total_cost_val += r["cost"]

    lines.append(f"  {'-' * 16} {'-' * 8} {'-' * 8} {'-' * 10}")
    lines.append(
        f"  {'total':<16s} {total_prompt:>8d} {total_completion:>8d} {total_cost_val:>10.6f}"
    )
    return "\n".join(lines)


def total_cost() -> float:
    return sum(r["cost"] for r in _records)
