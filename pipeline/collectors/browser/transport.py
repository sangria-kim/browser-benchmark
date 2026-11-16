"""Injectable HTTPS transport. Raw response caches belong outside the repository."""
from dataclasses import dataclass, field
from urllib.request import Request, urlopen


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
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read(self.max_bytes + 1)
            declared = response.headers.get('Content-Length')
            if declared and int(declared) != len(body) and len(body) <= self.max_bytes:
                raise ValueError('Truncated HTTP response')
            if len(body) > self.max_bytes:
                raise ValueError('Response byte limit reached')
            return Response(response.url, body, response.status,
                            {k.lower(): v for k, v in response.headers.items()})
