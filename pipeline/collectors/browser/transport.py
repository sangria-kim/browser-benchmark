"""Injectable HTTPS transport. Raw response caches belong outside the repository."""
from dataclasses import dataclass, field
from urllib.request import Request, urlopen
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

    def text(self):
        return self.body.decode('utf-8-sig')


class HTTPTransport:
    def __init__(self, timeout=30, max_bytes=64000000):
        self.timeout, self.max_bytes = timeout, max_bytes

    def __call__(self, url):
        if not url.startswith('https://'):
            raise ValueError('HTTPS required')
        request = Request(url, headers={'User-Agent': 'browser-benchmark/1.0 (public source research)',
                                        'Accept': 'application/json,text/html,text/plain;q=0.9'})
        for attempt in range(4):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read(self.max_bytes + 1)
                    declared = response.headers.get('Content-Length')
                    if declared and int(declared) != len(body) and len(body) <= self.max_bytes:
                        raise ValueError('Truncated HTTP response')
                    if len(body) > self.max_bytes:
                        raise ValueError('Response byte limit reached')
                    return Response(response.url, body, response.status,
                                    {k.lower(): v for k, v in response.headers.items()})
            except HTTPError as error:
                if error.code != 429 or attempt == 3:
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
