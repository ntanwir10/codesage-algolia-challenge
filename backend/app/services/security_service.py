# Phase 3 removes these no-op decorators together with their use in endpoints/ai.py.
# Real rate limiting lives in app.core.security.limiter.


def rate_limit_default(func):
    return func


def rate_limit_ai(func):
    return func
