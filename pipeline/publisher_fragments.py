"""Publisher element fragments and optional browser text highlights."""
import re
from urllib.parse import unquote, urlsplit


def publisher_fragment(url):
    raw = urlsplit(url).fragment
    element, _, directives = raw.partition(':~:')
    return unquote(element), [part[5:] for part in directives.split('&') if part.startswith('text=')]


def text_matches(text, directive):
    # Search within a publisher unit. Never guess a target across unverified
    # document layout. Split directive syntax before decoding its literal text.
    fields = directive.split(',')
    prefix = fields.pop(0)[:-1] if len(fields) > 1 and fields[0].endswith('-') else ''
    suffix = fields.pop()[1:] if len(fields) > 1 and fields[-1].startswith('-') else ''
    if len(fields) not in (1, 2) or not all(fields):
        return False
    def normalized(value):
        return ' '.join(value.casefold().split())
    def phrase(value):
        literal = normalized(unquote(value))
        if not literal:
            return None
        return re.compile((r'(?<!\w)' if literal[0].isalnum() else '') + re.escape(literal)
                          + (r'(?!\w)' if literal[-1].isalnum() else ''))
    start = phrase(fields[0])
    end = phrase(fields[1]) if len(fields) == 2 else None
    if start is None or len(fields) == 2 and end is None:
        return False
    text = normalized(text)
    before, after = normalized(unquote(prefix)), normalized(unquote(suffix))
    for match in start.finditer(text):
        if before and not text[:match.start()].rstrip().endswith(before):
            continue
        stops = end.finditer(text, match.end()) if end else (match,)
        if any(not after or text[stop.end():].lstrip().startswith(after) for stop in stops):
            return True
    return False
