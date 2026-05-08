"""Console logging utilities — clean, GBK-safe, structured output."""

import time

_start = 0.0


def start_timer():
    global _start
    _start = time.time()


def elapsed() -> str:
    secs = time.time() - _start
    if secs < 60:
        return f"{secs:.1f}s"
    return f"{int(secs // 60)}m{int(secs % 60)}s"


def section(label: str):
    print(f"\n{'=' * 56}")
    print(f"  {label}")
    print(f"{'-' * 56}")


def step(label: str, detail: str = ""):
    print(f"  >> {label}  {detail}".rstrip())


def ok(label: str, detail: str = ""):
    print(f"     {label}  {detail}".rstrip())


def warn(label: str, detail: str = ""):
    print(f"  !! {label}  {detail}".rstrip())


def done(label: str = ""):
    msg = f"  完成  {label}".rstrip()
    print(f"\n{'=' * 56}")
    print(msg)
    print(f"  耗时: {elapsed()}")
    print(f"{'=' * 56}")


def safe_print(text: str):
    """Print text safely on terminals that don't support Unicode (e.g. Windows GBK)."""
    try:
        print(text, end="", flush=True)
    except UnicodeEncodeError:
        print(
            text.encode("utf-8", errors="replace").decode("gbk", errors="replace"),
            end="",
            flush=True,
        )
