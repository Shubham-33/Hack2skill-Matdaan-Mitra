"""Security helpers — rate limiting, error sanitization.

The middleware that *applies* security headers + rate limit lives in `app.py`
because it depends on Flask's `request` proxy and registered hooks. The pure
helpers (which can be tested in isolation) live here.
"""

from __future__ import annotations

import re
import time
from typing import Final

# ---------------------------------------------------------------------------
# Constants — chat input + rate limit budgets
# ---------------------------------------------------------------------------

#: Hard cap on a single chat message. Longer than 2k chars is almost certainly
#: prompt-injection or junk; legit users don't type novels.
MAX_CHAT_MESSAGE_CHARS: Final[int] = 2000

#: Cap on conversation history sent with each request. Prevents context-window
#: abuse and keeps Gemini token costs predictable.
MAX_HISTORY_TURNS: Final[int] = 50

#: Sliding window for per-IP rate limiting. Generous enough that legit chatty
#: users don't hit it; restrictive enough to slow down obvious abuse.
RATE_LIMIT_WINDOW_S: Final[int] = 60
RATE_LIMIT_MAX_REQUESTS: Final[int] = 30


# ---------------------------------------------------------------------------
# Per-IP rate limit state (in-memory; production-grade would use Redis)
# ---------------------------------------------------------------------------

#: Map of `key` -> list of recent request timestamps. Mutated in place by
#: `rate_limit_check`. Tests reset this between runs via a conftest fixture.
RATE_LIMIT: dict[str, list[float]] = {}


def rate_limit_check(key: str, max_requests: int | None = None,
                    window_s: int | None = None) -> bool:
    """Return True if `key` is within rate limit, False if exceeded.

    Sliding window over the last `window_s` seconds. Defaults are looked up at
    call time (not function-definition time) so tests can monkey-patch the
    module-level constants.

    :param key: Bucket identifier (typically `"chat:<ip>"`).
    :param max_requests: Override for the cap. Falls back to
      :data:`RATE_LIMIT_MAX_REQUESTS` when None.
    :param window_s: Override for the window length in seconds. Falls back to
      :data:`RATE_LIMIT_WINDOW_S` when None.
    """
    cap = max_requests if max_requests is not None else RATE_LIMIT_MAX_REQUESTS
    win = window_s if window_s is not None else RATE_LIMIT_WINDOW_S
    now = time.time()
    window_start = now - win
    bucket = RATE_LIMIT.setdefault(key, [])
    bucket[:] = [t for t in bucket if t > window_start]  # drop expired
    if len(bucket) >= cap:
        return False
    bucket.append(now)
    return True


# ---------------------------------------------------------------------------
# Error message sanitization
# ---------------------------------------------------------------------------

#: Pattern that matches Google API key URL params. Used to redact keys before
#: error strings travel back to clients in a 5xx body.
_API_KEY_URL_PARAM_RE: Final[re.Pattern[str]] = re.compile(
    r"[?&]key=[A-Za-z0-9_\-]+"
)


def safe_error(exc: Exception) -> str:
    """Convert an exception to a short, key-redacted string for client responses.

    We never want a Gemini 5xx body or a raw URL containing `?key=AIzaSy...`
    to reach the browser. This trims to 200 chars and substitutes any matched
    key parameter with `?key=REDACTED`.
    """
    msg = str(exc)[:500]
    return _API_KEY_URL_PARAM_RE.sub("?key=REDACTED", msg)[:200]
