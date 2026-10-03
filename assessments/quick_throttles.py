import hashlib
from collections.abc import Mapping

from django.utils.crypto import salted_hmac
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class QuickVerifyIPThrottle(SimpleRateThrottle):
    scope = "quick_verify_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": hashlib.sha256(self.get_ident(request).encode()).hexdigest()}


class QuickVerifyIdentifierThrottle(SimpleRateThrottle):
    scope = "quick_verify_identifier"

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, Mapping) else {}
        code = str(data.get("exam_code", ""))[:128].strip().upper()
        candidate = str(data.get("candidate_id", ""))[:128].strip().casefold()
        # Bind to IP: no global candidate lockout. Length-prefix each component.
        parts = (self.get_ident(request), code, candidate)
        digest = salted_hmac("quick-exam-verification", "".join(f"{len(part)}:{part}" for part in parts), algorithm="sha256").hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class QuickSessionThrottle(ScopedRateThrottle):
    def get_cache_key(self, request, view):
        session_id = request.auth.quick_session.pk
        return self.cache_format % {"scope": self.scope, "ident": f"quick-session-{session_id}"}
