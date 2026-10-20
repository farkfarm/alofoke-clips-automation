from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..errors import ProviderError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("provider HTTP redirect rejected")


class JsonHTTP:
    def request(
        self, url: str, payload: dict[str, Any] | None, timeout: float, token: str | None = None
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        # Ignore proxy environment variables and never forward credentials across redirects.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(10 * 1024 * 1024 + 1)
            if len(raw) > 10 * 1024 * 1024:
                raise ProviderError("provider response exceeds 10 MiB")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ProviderError("provider must return a JSON object")
            return result
        except urllib.error.HTTPError as error:
            raise ProviderError(f"provider HTTP {error.code}; response body omitted") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProviderError(
                f"provider connection failed: {error.__class__.__name__}"
            ) from error
        except (ValueError, UnicodeError) as error:
            raise ProviderError("provider returned invalid JSON") from error
