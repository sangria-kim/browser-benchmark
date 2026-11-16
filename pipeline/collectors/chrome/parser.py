"""Conservative lexical Chromium definition parser (not a C++ compiler).

Each recognized candidate has one disposition. Unsupported candidate syntax is
retained, never counted as parsed. Preprocessor branches are kept, not evaluated.
"""
import json
import hashlib
from functools import lru_cache
import re
from dataclasses import dataclass, field

TOKEN = re.compile(r'R"(?P<delim>[^ ()\\\t\r\n]{0,16})\(.*?\)(?P=delim)"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.S)
IDENT = r'[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*'


def strip_comments(text):
    return TOKEN.sub(lambda m: re.sub(r'[^\n]', ' ', m[0]) if m[0].startswith(('//', '/*')) else m[0], text)


@lru_cache(maxsize=8)
def masked(text):
    return TOKEN.sub(lambda m: re.sub(r'[^\n]', ' ', m[0]), text)


def matching(text, start):
    pairs = {'(': ')', '{': '}', '[': ']'}
    clean = masked(text)
    stack = []
    for pos in range(start, len(text)):
        ch = clean[pos]
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in ')}]':
            if not stack or stack.pop() != ch:
                return None
            if not stack:
                return pos
    return None


def arguments(text):
    clean, result, start, depth = masked(text), [], 0, 0
    for pos, ch in enumerate(clean):
        if ch in '({[':
            depth += 1
        elif ch in ')}]':
            depth -= 1
        elif ch == ',' and depth == 0:
            result.append(text[start:pos].strip())
            start = pos + 1
    if text[start:].strip():
        result.append(text[start:].strip())
    return result


def literal(value):
    value = value.strip()
    if re.fullmatch(r'(?:L?"(?:\\.|[^"\\])*"\s*)+', value):
        try:
            return ''.join(json.loads(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', value))
        except ValueError:
            return None
    return None


def safe_excerpt(text, size=1000):
    text = strip_comments(text)
    text = re.sub(r'[^\s"<>]+@[^\s"<>]+', '[contact omitted]', text)
    return ' '.join(text.split())[:size]


def conditions_at(text, offset):
    stack = []
    for line in text[:offset].splitlines():
        m = re.match(r'\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)', line)
        if not m:
            continue
        directive, value = m[1], m[2].strip()
        if directive in ('if', 'ifdef', 'ifndef'):
            expr = value if directive == 'if' else ('!' if directive == 'ifndef' else '') + 'defined(' + value + ')'
            stack.append({'seen': [expr], 'active': expr})
        elif directive in ('else', 'elif') and stack:
            prior = ' || '.join('(' + v + ')' for v in stack[-1]['seen'])
            stack[-1]['active'] = '!(' + prior + ')' + (' && (' + value + ')' if directive == 'elif' else '')
            if directive == 'elif':
                stack[-1]['seen'].append(value)
        elif directive == 'endif' and stack:
            stack.pop()
    return list(dict.fromkeys(s['active'] for s in stack))


def namespace_at(text, offset):
    found = []
    for m in re.finditer(r'\bnamespace\s+([\w:]+)\s*\{', masked(text[:offset])):
        end = matching(text, text.index('{', m.start()))
        if end is not None and end > offset:
            found.append(m[1])
    return '::'.join(found)


@dataclass
class Candidate:
    kind: str
    symbol: str
    path: str
    line: int
    end_line: int
    expression: str
    conditions: list = field(default_factory=list)
    parsed: bool = False
    value: object = None
    default: object = None
    refs: list = field(default_factory=list)
    alias: object = None
    platforms: list = field(default_factory=list)
    title_ref: object = None
    description_ref: object = None
    options: list = field(default_factory=list)
    namespace: str = ''
    registered: bool = False

    @property
    def qualified_symbol(self):
        return self.namespace + '::' + self.symbol if self.namespace else self.symbol


def parse(path, original):
    text = strip_comments(original)
    candidates, declarations, covered, diagnostics = [], [], [], []
    namespace_spans = []
    clean = masked(text)
    for match in re.finditer(r'\bnamespace\s+([\w:]+)\s*\{', clean):
        end = matching(text, text.index('{', match.start()))
        if end is not None:
            namespace_spans.append((match.start(), end, match[1]))

    def namespace(offset):
        return '::'.join(name for start, end, name in namespace_spans if start < offset < end)

    def add(kind, symbol, start, end, **kw):
        if symbol.startswith('unresolved-line-'):
            symbol = 'unresolved-' + hashlib.sha256(safe_excerpt(text[start:end], None).encode()).hexdigest()[:20]
        c = Candidate(kind, symbol, path, text.count('\n', 0, start) + 1,
                      text.count('\n', 0, end) + 1, safe_excerpt(text[start:end], None),
                      conditions_at(text, start), namespace=namespace(start), registered=kind == 'flag_entry', **kw)
        candidates.append(c)
        covered.append((start, end))
        return c

    # Macro definitions are templates, not instantiated feature definitions.
    preprocess = [(m.start(), m.end()) for m in re.finditer(r'^\s*#\s*define\b(?:[^\n\\]|\\\n)*', text, re.M)]
    for m in re.finditer(r'\b(BASE_FEATURE|BASE_DECLARE_FEATURE)\s*\(', masked(text)):
        if any(a <= m.start() < b for a, b in preprocess):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'macro_template'})
            covered.append((m.start(), m.end()))
            continue
        start = text.index('(', m.start())
        end = matching(text, start)
        end = end + 1 if end is not None else text.find('\n', start)
        if end < start:
            end = len(text)
        args = arguments(text[start + 1:end - 1])
        symbol = args[0] if args and re.fullmatch(IDENT, args[0]) else 'unresolved-line-' + str(text.count('\n', 0, m.start()) + 1)
        if m[1] == 'BASE_DECLARE_FEATURE':
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'feature_declaration'})
            covered.append((m.start(), end))
            continue
        default = args[-1] if len(args) in (2, 3) and re.fullmatch(r'(?:base::)?FEATURE_(?:ENABLED|DISABLED)_BY_DEFAULT', args[-1]) else None
        value = literal(args[1]) if len(args) == 3 else (symbol[1:] if len(args) == 2 and symbol.startswith('k') else None)
        add('base_feature', symbol, m.start(), end, parsed=default is not None and value is not None,
            value=value, default=default)

    # Direct definitions and aliases; exclude extern declarations and type uses.
    direct = r'\bbase::Feature\s*(&?)\s+(' + IDENT + r')\s*([={;(])'
    for m in re.finditer(direct, masked(text)):
        if any(a <= m.start() < b for a, b in covered):
            continue
        end = text.find(';', m.end())
        end = len(text) if end < 0 else end + 1
        prefix = text[max(0, text.rfind('\n', 0, m.start())):m.start()]
        if m[3] == ';' or re.search(r'\bextern\b', prefix):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'feature_declaration'})
            covered.append((m.start(), end))
            continue
        body = text[m.end() - 1:end].strip().rstrip(';').strip().lstrip('=').strip()
        alias = body if m[1] and re.fullmatch(IDENT, body) else None
        args = arguments(body[1:-1]) if body.startswith(('{', '(')) else []
        default = args[-1] if len(args) == 2 and re.fullmatch(r'(?:base::)?FEATURE_(?:ENABLED|DISABLED)_BY_DEFAULT', args[-1]) else None
        value = literal(args[0]) if args else None
        add('base_feature', m[2], m.start(), end, parsed=bool(alias or (default and value)), value=value,
            default=default, alias=alias, refs=[alias] if alias else [])

    # Named flag table initializer: inspect every top-level row, even unknown ones.
    for m in re.finditer(r'\b(?:kFeatureEntries|kFeatureEntry)\s*(?:\[\s*\])?\s*=\s*(?:std::to_array<[^>]+>\s*\(\s*)?\{', masked(text)):
        start = text.rfind('{', m.start(), m.end())
        terminator = re.search(r'^\s*}\s*\)?;', text[start + 1:], re.M)
        finish = start + 1 + terminator.start() if terminator else matching(text, start)
        if finish is None:
            diagnostics.append('unterminated_flag_table')
            finish = len(text)
        pos = start + 1
        while pos < finish:
            # Directives between rows are retained through conditions_at.
            skip = re.match(r'\s*(?:#[^\n]*\n|,)', text[pos:finish])
            if skip:
                pos += skip.end()
                continue
            if text[pos].isspace():
                pos += 1
                continue
            if text[pos] == '{':
                end = matching(text, pos)
                if end is None:
                    end = finish - 1
                args = arguments(text[pos + 1:end])
                symbol = (literal(args[0]) or (args[0] if re.fullmatch(IDENT, args[0]) else None)) if args else None
                symbol = symbol or 'unresolved-line-' + str(text.count('\n', 0, pos) + 1)
                body = ', '.join(args[4:])
                refs = re.findall(r'\b(?:[A-Za-z_]\w*::)*k[A-Z]\w*\b', body)
                macro = re.match(r'([A-Z_]+)\s*\(', body)
                supported = {'FEATURE_VALUE_TYPE', 'FEATURE_WITH_PARAMS_VALUE_TYPE', 'SINGLE_VALUE_TYPE',
                             'SINGLE_DISABLE_VALUE_TYPE', 'SINGLE_VALUE_TYPE_AND_VALUE', 'MULTI_VALUE_TYPE',
                             'ENABLE_DISABLE_VALUE_TYPE', 'ENABLE_DISABLE_VALUE_TYPE_AND_VALUE',
                             'ORIGIN_LIST_VALUE_TYPE', 'STRING_VALUE_TYPE', 'PLATFORM_FEATURE_NAME_TYPE',
                             'PLATFORM_FEATURE_NAME_WITH_PARAMS_VALUE_TYPE'}
                c = add('flag_entry', symbol, pos, end + 1, parsed=len(args) >= 5 and not symbol.startswith('unresolved-') and bool(macro and macro[1] in supported),
                        value=literal(args[0]) if args else None, refs=refs, platforms=list(dict.fromkeys(re.findall(r'kOs\w+', args[3]))) if len(args) > 3 else [],
                        title_ref=args[1] if len(args) > 1 else None, description_ref=args[2] if len(args) > 2 else None,
                        options=[safe_excerpt(body)] if body else [])
                pos = end + 1
            else:
                end = text.find('\n', pos, finish)
                end = finish if end < 0 else end
                add('flag_entry', 'unresolved-line-' + str(text.count('\n', 0, pos) + 1), pos, end)
                pos = end + 1

    # Switches have no central registry. Inspect string definitions in switch
    # paths or a switches namespace. Other string constants are not switches.
    for m in re.finditer(r'\b(?:const|constexpr)\s+(?:char|wchar_t)\s+(' + IDENT + r')\s*\[\s*\]\s*([=;])', masked(text)):
        ns = namespace(m.start())
        if 'switch' not in path.lower() and 'switches' not in ns.split('::'):
            continue
        if m[2] == ';':
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'switch_declaration'})
            continue
        end = text.find(';', m.end())
        end = len(text) if end < 0 else end + 1
        rhs = text[m.end():end].rstrip(';').strip()
        value = literal(rhs)
        alias = rhs if re.fullmatch(IDENT, rhs) else None
        add('command_switch', m[1], m.start(), end, parsed=value is not None or alias is not None,
            value=value, alias=alias, refs=[alias] if alias else [])

    # Preserve unsupported string-definition syntax in the switch scope too.
    # The independent marker pass catches pointers, sized arrays and modifiers.
    for m in re.finditer(r'\b(?:const|constexpr)\s+(?:char|wchar_t)\b', masked(text)):
        ns = namespace(m.start())
        if 'switch' not in path.lower() and 'switches' not in ns.split('::'):
            continue
        if any(a <= m.start() < b for a, b in covered):
            continue
        end = text.find(';', m.end())
        end = len(text) if end < 0 else end + 1
        expression = text[m.start():end]
        if '=' not in expression:
            continue  # Forward declarations do not define a switch.
        symbol_match = re.search(r'\b(k[A-Z]\w*)\b', expression)
        symbol = symbol_match[1] if symbol_match else 'unresolved-line-' + str(text.count('\n', 0, m.start()) + 1)
        add('command_switch', symbol, m.start(), end)

    # Catch unhandled feature forms independently of supported-definition regex.
    # Known type uses/declarations are accounted separately, not invented features.
    for m in re.finditer(r'\b(?:BASE_FEATURE|BASE_DECLARE_FEATURE|base::Feature)\b', masked(text)):
        if any(a <= m.start() < b for a, b in covered):
            continue
        tail = text[m.end():text.find('\n', m.end()) if '\n' in text[m.end():] else len(text)]
        if re.match(r'\s*(?:[>*]|::|[&*]?\s*[,)>])', tail):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'feature_type_use'})
        else:
            end = text.find('\n', m.end())
            add('base_feature', 'unresolved-line-' + str(text.count('\n', 0, m.start()) + 1), m.start(), end if end >= 0 else len(text))
    return candidates, declarations, diagnostics


def auxiliary_definitions(text):
    """Minimal initializers for titles, choice tables, variations and parameters."""
    text = strip_comments(text)
    result = {}
    spans = []
    for match in re.finditer(r'\bnamespace\s+([\w:]+)\s*\{', masked(text)):
        end = matching(text, text.index('{', match.start()))
        if end is not None:
            spans.append((match.start(), end, match[1]))
    for m in re.finditer(r'\b(k[A-Z]\w*)\s*(?:\[[^\]]*\])?\s*=', masked(text)):
        start = m.end()
        while start < len(text) and text[start].isspace():
            start += 1
        if start >= len(text):
            continue
        end = matching(text, start) if text[start] == '{' else text.find(';', start)
        if end is None or end < 0:
            continue
        expr = text[start:end + (text[start] == '{')].strip()
        namespace = '::'.join(name for start, end, name in spans if start < m.start() < end)
        result.setdefault(m[1], []).append({'namespace': namespace, 'expression': safe_excerpt(expr, None), 'value': literal(expr),
                                            'refs': re.findall(r'\b(?:[A-Za-z_]\w*::)*k[A-Z]\w*\b', masked(expr)),
                                            'path_line': text.count('\n', 0, m.start()) + 1})
    return result
