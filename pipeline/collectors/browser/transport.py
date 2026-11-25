"""Injectable HTTPS transport. Raw response caches belong outside the repository."""
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from urllib.error import HTTPError
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import time


@dataclass
class Response:
    url: str
    body: bytes
    status: int = 200
    headers: dict = field(default_factory=dict)
    observed_at: Optional[str] = None

    def text(self):
        return self.body.decode('utf-8-sig')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPTransport:
    def __init__(self, timeout=30, max_bytes=64000000):
        self.timeout, self.max_bytes = timeout, max_bytes

    def get_once(self, url, before_send):
        """Let a source handle its own Retry-After checkpoint and deadline."""
        return self(url, single_attempt=True, before_send=before_send)

    def __call__(self, url, *, direct=False, if_modified_since=None, before_send=None, single_attempt=False):
        if not url.startswith('https://'):
            raise ValueError('HTTPS required')
        headers = {'User-Agent': 'browser-benchmark/1.0 (public source research)',
                   'Accept': 'application/json,text/html,text/plain;q=0.9'}
        if if_modified_since is not None:
            if not direct:
                raise ValueError('Conditional evidence requires a direct request')
            headers['If-Modified-Since'] = if_modified_since
        if direct:
            headers['Accept-Encoding'] = 'identity'
            headers['Cache-Control'] = 'no-cache'
        request = Request(url, headers=headers)
        opener = build_opener(NoRedirect()).open if direct or single_attempt else urlopen
        attempts = 1 if single_attempt else 4
        for attempt in range(attempts):
            try:
                if before_send is not None:
                    before_send()
                with opener(request, timeout=self.timeout) as response:
                    body = response.read(self.max_bytes + 1)
                    declared = response.headers.get('Content-Length')
                    if declared and int(declared) != len(body) and len(body) <= self.max_bytes:
                        raise ValueError('Truncated HTTP response')
                    if len(body) > self.max_bytes:
                        raise ValueError('Response byte limit reached')
                    return Response(response.url, body, response.status,
                                    response.headers if direct else {k.lower(): v for k, v in response.headers.items()})
            except HTTPError as error:
                if error.code == 304 and if_modified_since is not None:
                    with error:
                        return Response(error.url, error.read(1), 304, error.headers)
                if error.code != 429 or attempt + 1 == attempts:
                    raise
                delay = 30 * 2 ** attempt
                value = error.headers.get('Retry-After') if error.headers else None
                if value:
                    try:
                        required = int(value) if value.isdigit() else (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                        delay = max(delay, required)
                    except (ValueError, TypeError):
                        raise error
                if delay > 180:
                    # Leave the source partial for a later retry rather than
                    # violate the publisher's requested delay or wait unbounded.
                    raise
                while delay > 0:
                    pause = min(delay, 60)
                    time.sleep(pause)
                    delay -= pause
