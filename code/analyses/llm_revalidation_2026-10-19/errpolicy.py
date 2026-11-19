import re

def redact(s):
    return re.sub(r"(sk-[A-Za-z0-9_\-]{6,}|AIza[A-Za-z0-9_\-]{10,}|key=[^&\s]+)", "[redacted]", s)

def classify(e):
    msg = f"{type(e).__name__} {e}"
    low = msg.lower().replace(" ", "")
    short = redact(" ".join(msg.split()))[:300]
    if "429" in low or "resource_exhausted" in low or "ratelimit" in low or "overloaded" in low or "529" in low:
        if "perday" in low or "requestsperday" in low or "insufficient_quota" in low:
            return "permanent", short
        return "retry_long", short
    for k in ("invalid_api_key", "invalidx-api-key", "apikeynotvalid", "authentication", "permission_denied",
              "permissiondenied", "not_found", "notfound", "model_not_found", "insufficient_quota"):
        if k in low:
            return "permanent", short
    if "clienthasbeenclosed" in low:
        return "permanent", short
    if "400" in low or "invalid_argument" in low or "badrequest" in low:
        return "permanent", short
    return "retry", short
