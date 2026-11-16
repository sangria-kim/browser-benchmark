"""Conservative lexical Chromium definition parser (not a C++ compiler).

Each recognized candidate has one disposition. Unsupported candidate syntax is
retained, never counted as parsed. Preprocessor branches are kept, not evaluated.
"""
import json
import hashlib
import ast
import itertools
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
    if text[start] == '{':
        # A namespace/initializer brace span must not be truncated by mutually
        # exclusive preprocessor arms that each close a surrounding macro call.
        depth, branches = 0, []
        tokens = re.compile(r'^[ \t]*#[ \t]*(if|ifdef|ifndef|elif|else|endif)\b(?:[^\n\\]|\\\n)*|[{}]', re.M)
        for token in tokens.finditer(clean, start):
            kind = token[1]
            if kind in {'if', 'ifdef', 'ifndef'}:
                branches.append({'start': depth, 'ends': [], 'else': False})
            elif kind in {'elif', 'else'} and branches:
                branch = branches[-1]
                branch['ends'].append(depth)
                depth = branch['start']
                branch['else'] |= kind == 'else'
            elif kind == 'endif' and branches:
                branch = branches.pop()
                ends = branch['ends'] + [depth] + ([] if branch['else'] else [branch['start']])
                if len(set(ends)) != 1:
                    return None
                depth = ends[0]
            elif not kind:
                depth += 1 if token[0] == '{' else -1
            if depth == 0 and not branches:
                return token.end() - 1
        return None
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
    raw = re.fullmatch(r'R"([^ ()\\\t\r\n]{0,16})\((.*)\)\1"', value, re.S)
    if raw:
        return raw[2]
    if re.fullmatch(r'(?:L?"(?:\\.|[^"\\])*"\s*)+', value):
        try:
            return ''.join(ast.literal_eval(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', value))
        except (ValueError, SyntaxError):
            return None
    return None


def conditional_end(text, start, end):
    """Include the other arms when a declaration closes inside an #if arm."""
    depth = 0
    for m in re.finditer(r'^\s*#\s*(if|ifdef|ifndef|endif)\b[^\n]*', text[start:end + 1], re.M):
        depth += -1 if m[1] == 'endif' else 1
    if depth > 0:
        for m in re.finditer(r'^\s*#\s*(if|ifdef|ifndef|endif)\b[^\n]*', text[end + 1:], re.M):
            depth += -1 if m[1] == 'endif' else 1
            if depth == 0:
                return end + 1 + m.end() - 1
    return end


def conditional_variants(text):
    """Expand only directives inside one declaration, retaining each condition.

    This does not evaluate build flags or generate a translation-unit cross
    product. Every arm in the source declaration remains a separate candidate.
    """
    lines = text.replace('\\\n', ' ').splitlines(keepends=True)
    def section(index, stop=False):
        variants = [('', [])]
        while index < len(lines):
            directive = re.match(r'\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)', lines[index])
            if directive and directive[1] in {'elif', 'else', 'endif'}:
                return variants, index
            if directive:
                kind, expression = directive[1], directive[2].strip()
                expression = expression if kind == 'if' else ('!' if kind == 'ifndef' else '') + 'defined(' + expression + ')'
                arms, prior, has_else = [], [], False
                while True:
                    branch, ending = section(index + 1, True)
                    condition = ('!(' + ' || '.join('(' + p + ')' for p in prior) + ')' if prior else '')
                    if expression:
                        condition += (' && ' if condition else '') + '(' + expression + ')'
                    arms.extend((body, [condition] + conditions) for body, conditions in branch)
                    prior.append(expression)
                    if ending >= len(lines):
                        raise ValueError('Unterminated conditional declaration')
                    end = re.match(r'\s*#\s*(elif|else|endif)\b(.*)', lines[ending])
                    if end[1] == 'endif':
                        if not has_else:
                            # Preprocessing keeps the surrounding declaration
                            # when no condition matches, even without an explicit
                            # else. Preserve that empty arm and its condition.
                            arms.append(('', ['!(' + ' || '.join('(' + p + ')' for p in prior) + ')']))
                        index = ending + 1
                        break
                    has_else |= end[1] == 'else'
                    index, expression = ending, end[2].strip() if end[1] == 'elif' else ''
                variants = [(left + right, a + b) for left, a in variants for right, b in arms]
                if len(variants) > 256:
                    raise ValueError('Conditional declaration expansion limit')
            else:
                variants = [(body + lines[index], conditions) for body, conditions in variants]
                index += 1
        return variants, index
    return section(0)[0]


def safe_excerpt(text, size=1000):
    text = strip_comments(text)
    if '@' in text:
        text = re.sub(r'[^\s"<>]+@[^\s"<>]+', '[contact omitted]', text)
    return ' '.join(text.split())[:size]


def conditions_at(text, offset):
    stack = []
    for line in text[:offset].replace('\\\n', ' ').splitlines():
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


def impossible_conditions(conditions):
    """Reject only provably unreachable Boolean preprocessor arms."""
    return _impossible_conditions(tuple(conditions))


@lru_cache(maxsize=8192)
def _impossible_conditions(conditions):
    atoms = {}
    expressions = []
    for condition in conditions:
        expression = re.sub(r'BUILDFLAG\(\w+\)|defined\(\w+\)|\b[A-Za-z_]\w*\b',
                            lambda m: atoms.setdefault(m[0], 'v' + str(len(atoms))), condition)
        if re.search(r'[^v0-9\s()!&|]', expression) or len(atoms) > 12:
            return False
        try:
            tree = ast.parse(expression.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ').strip(), mode='eval')
        except SyntaxError:
            return False
        if any(not isinstance(n, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Name, ast.Load, ast.Constant)) for n in ast.walk(tree)):
            return False
        expressions.append(compile(tree, '<build-condition>', 'eval'))
    return bool(expressions) and not any(all(eval(e, {'__builtins__': {}}, dict(zip(atoms.values(), values))) for e in expressions)
                                        for values in itertools.product((False, True), repeat=len(atoms)))


def namespace_at(text, offset):
    found = []
    for m in re.finditer(r'\bnamespace\s+([\w:]+)\s*\{', masked(text[:offset])):
        end = matching(text, text.index('{', m.start()))
        if end is not None and end > offset:
            found.append(m[1])
    return '::'.join(found)


def references(text):
    # Anchor whitespace to an identifier. An unanchored \s* pattern retries
    # every suffix of large masked comment blocks and becomes quadratic.
    clean = re.sub(r'(?<=\w)\s*::\s*', '::', masked(text))
    return re.findall(r'\b(?:[A-Za-z_]\w*::)*k[A-Z]\w*\b', clean)


def semantic_expression(text):
    # C++ whitespace/comments outside literals have no definition meaning.
    clean = strip_comments(text)
    tokens = re.findall(r'R"[^ ()\\\t\r\n]{0,16}\(.*?\)[^ ()\\\t\r\n]{0,16}"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|\d+(?:\.\d+)?|::|&&|\|\||==|!=|<=|>=|<<|>>|\+\+|--|->|[^\s]', clean, re.S)
    return ' '.join(tokens)


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
    value_ref: object = None

    @property
    def qualified_symbol(self):
        return self.namespace + '::' + self.symbol if self.namespace else self.symbol


def parse(path, original, *, mojo_default_disabled=False):
    if path.endswith('.mojom'):
        return parse_mojom(path, original, mojo_default_disabled)
    if not any(marker in original for marker in ('BASE_FEATURE', 'BASE_DECLARE_FEATURE', 'base::Feature', 'kFeatureEntries', 'kFeatureEntry', 'switches')) and 'switch' not in path.lower():
        return [], [], []
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
    for m in re.finditer(r'\b(BASE_FEATURE_WITH_COUNTRY_RESTRICTIONS|BASE_FEATURE|BASE_DECLARE_FEATURE)\s*\(', masked(text)):
        if any(a <= m.start() < b for a, b in preprocess):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'macro_template'})
            covered.append((m.start(), m.end()))
            continue
        start = text.index('(', m.start())
        end = matching(text, start)
        end = conditional_end(text, start, end) + 1 if end is not None else text.find('\n', start)
        if end < start:
            end = len(text)
        if m[1] == 'BASE_DECLARE_FEATURE':
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'feature_declaration'})
            covered.append((m.start(), end))
            continue
        try:
            variants = conditional_variants(text[m.start():end])
        except ValueError:
            variants = [(text[m.start():end], [])]
        for expression, conditions in variants:
            opening = expression.index('(')
            closing = matching(expression, opening)
            args = arguments(expression[opening + 1:closing]) if closing is not None else []
            if args:
                args[0] = re.sub(r'\s*::\s*', '::', args[0])
            symbol = args[0] if args and re.fullmatch(IDENT, args[0]) else 'unresolved-line-' + str(text.count('\n', 0, m.start()) + 1)
            # A source default can be a symbolic constant, function or ternary.
            # Preserve its expression; it is not an evaluated runtime state.
            country = m[1] == 'BASE_FEATURE_WITH_COUNTRY_RESTRICTIONS'
            default = ', '.join(args[1:]) if country and len(args) >= 3 else args[-1] if len(args) in (2, 3) and '#' not in args[-1] else None
            value = literal(args[1]) if len(args) == 3 and not country else (symbol[1:] if symbol.startswith('k') else symbol)
            valid_name = country and len(args) >= 3 or len(args) == 2 or len(args) == 3 and (value is not None or re.fullmatch(IDENT, args[1]))
            candidate = add('base_feature', symbol, m.start(), end,
                            parsed=bool(default and valid_name and not symbol.startswith('unresolved-')),
                            value=value, default=default)
            if len(args) == 3 and not country and value is None and re.fullmatch(IDENT, args[1]):
                candidate.value_ref = args[1]
            candidate.conditions.extend(conditions)

    # Local feature wrappers retain every preprocessor arm and the expanded
    # definition. Resolve only a single-argument macro with one feature body.
    # This covers country-restricted Autofill and Sync wrappers without guessing
    # the meaning of an arbitrary macro invocation.
    wrappers = {}
    for directive in re.finditer(r'^\s*#\s*define\b(?:[^\n\\]|\\\n)*', text, re.M):
        m = re.match(r'\s*#\s*define\s+(\w+)(\(([^)]*)\))?(.*)', directive[0].replace('\\\n', ' '), re.S)
        body = m[4].strip()
        if m[2] and re.fullmatch(r'\w+', m[3].strip()) and re.fullmatch(r'BASE_FEATURE(?:_WITH_COUNTRY_RESTRICTIONS)?\s*\(.*\)', body, re.S):
            wrappers.setdefault(m[1], []).append((m[3].strip(), body, conditions_at(text, directive.start())))
    for name, definitions in wrappers.items():
        for use in re.finditer(r'\b' + re.escape(name) + r'\s*\(\s*(' + IDENT + r')\s*\)', masked(text)):
            if any(a <= use.start() < b for a, b in preprocess):
                continue
            for parameter, body, conditions in definitions:
                # Substitute the argument token only. Leave object macro names
                # for the condition-aware resolver; never pick their last body.
                expanded = body
                for token in reversed(list(re.finditer(r'\b' + parameter + r'\b', masked(body)))):
                    expanded = expanded[:token.start()] + use[1] + expanded[token.end():]
                values, _, issues = parse(path, expanded + ';')
                if len(values) == 1 and not issues:
                    value = values[0]
                    candidate = add('base_feature', use[1], use.start(), use.end(), parsed=value.parsed,
                                    value=value.value, default=value.default, refs=value.refs)
                    candidate.expression = value.expression
                    candidate.value_ref = value.value_ref
                    candidate.conditions.extend(c for c in conditions if c not in candidate.conditions)
                else:
                    add('base_feature', use[1], use.start(), use.end())

    # Direct definitions and aliases; exclude extern declarations and type uses.
    direct = r'\bbase::Feature\s*(&?)\s+(' + IDENT + r')\s*([={;(])'
    for m in re.finditer(direct, masked(text)):
        if any(a <= m.start() < b for a, b in covered):
            continue
        if any(a <= m.start() < b for a, b in preprocess):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'macro_template'})
            covered.append((m.start(), m.end()))
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
        if m[1] and alias is None:
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'feature_reference_use'})
            covered.append((m.start(), end))
            continue
        args = arguments(body[1:-1]) if body.startswith(('{', '(')) else []
        default = args[-1] if len(args) == 2 and re.fullmatch(r'(?:base::)?FEATURE_(?:ENABLED|DISABLED)_BY_DEFAULT', args[-1]) else None
        value = literal(args[0]) if args else None
        add('base_feature', m[2], m.start(), end, parsed=bool(alias or (default and value)), value=value,
            default=default, alias=alias, refs=[alias] if alias else [])

    def add_flag(args, pos, end, conditions):
        symbol = (literal(args[0]) or (args[0] if re.fullmatch(IDENT, args[0]) else None)) if args else None
        symbol = symbol or 'unresolved-line-' + str(text.count('\n', 0, pos) + 1)
        body = ', '.join(args[4:])
        refs = references(body)
        macro = re.match(r'([A-Z_]+)\s*\(', body)
        supported = {'FEATURE_VALUE_TYPE', 'FEATURE_WITH_PARAMS_VALUE_TYPE', 'SINGLE_VALUE_TYPE',
                     'SINGLE_DISABLE_VALUE_TYPE', 'SINGLE_VALUE_TYPE_AND_VALUE', 'MULTI_VALUE_TYPE',
                     'ENABLE_DISABLE_VALUE_TYPE', 'ENABLE_DISABLE_VALUE_TYPE_AND_VALUE',
                     'ORIGIN_LIST_VALUE_TYPE', 'STRING_VALUE_TYPE', 'PLATFORM_FEATURE_NAME_TYPE',
                     'PLATFORM_FEATURE_NAME_WITH_PARAMS_VALUE_TYPE', 'PLATFORM_FEATURE_WITH_PARAMS_VALUE_TYPE'}
        c = add('flag_entry', symbol, pos, end + 1, parsed=len(args) >= 5 and not symbol.startswith('unresolved-') and bool(macro and macro[1] in supported),
                value=literal(args[0]) if args else None, refs=refs, platforms=list(dict.fromkeys(re.findall(r'kOs\w+', args[3]))) if len(args) > 3 else [],
                title_ref=args[1] if len(args) > 1 else None, description_ref=args[2] if len(args) > 2 else None,
                options=[safe_excerpt(body)] if body else [])
        c.conditions.extend(conditions)

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
            skip = re.match(r'\s*(?:#(?:[^\n\\]|\\\n)*\n|,)', text[pos:finish])
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
                end = conditional_end(text, pos, end)
                variants = conditional_variants(text[pos:end + 1])
                for expression, conditions in variants:
                    closing = matching(expression, expression.index('{'))
                    args = arguments(expression[expression.index('{') + 1:closing]) if closing is not None else []
                    add_flag(args, pos, end, conditions)
                pos = end + 1
            else:
                end = text.find('\n', pos, finish)
                end = finish if end < 0 else end
                add('flag_entry', 'unresolved-line-' + str(text.count('\n', 0, pos) + 1), pos, end)
                pos = end + 1
    # Switches have no central registry. Inspect string definitions in switch
    # paths or a switches namespace. Other string constants are not switches.
    for m in re.finditer(r'\b(?:const|constexpr)\s+(?:char|wchar_t)(?:\s*\*\s*(?:const\s+)?(' + IDENT + r')|\s+(' + IDENT + r')\s*\[\s*\])\s*([=;])', masked(text)):
        if any(a <= m.start() < b for a, b in preprocess):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'macro_template'})
            covered.append((m.start(), m.end()))
            continue
        ns = namespace(m.start())
        if 'switch' not in path.lower() and 'switches' not in ns.split('::'):
            continue
        if m[3] == ';':
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'switch_declaration'})
            continue
        end = masked(text).find(';', m.end())
        end = len(text) if end < 0 else end + 1
        rhs = text[m.end():end].rstrip(';').strip()
        value = literal(rhs)
        alias = rhs if re.fullmatch(IDENT, rhs) else None
        symbol = m[1] or m[2]
        if m[1] and value is None and alias is None and not symbol.startswith('k'):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'runtime_string_use'})
            covered.append((m.start(), end))
            continue
        add('command_switch', symbol, m.start(), end, parsed=value is not None or alias is not None,
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
        tail = text[m.end():end]
        if re.match(r'\s*\*\s*(?:const\s*)?[>&]', tail) or re.match(r'\s*\*\s*(?:const\s+)?\w+\s*[,)>]', tail):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'string_type_use'})
            continue
        if re.match(r'\s*\*\s*(?:const\s+)?\w+\s*\[', tail):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'string_collection'})
            continue
        if '=' not in expression:
            continue  # Forward declarations do not define a switch.
        symbol_match = re.search(r'\b(k[A-Z]\w*)\b', expression)
        symbol = symbol_match[1] if symbol_match else 'unresolved-line-' + str(text.count('\n', 0, m.start()) + 1)
        add('command_switch', symbol, m.start(), end)

    # Catch unhandled feature forms independently of supported-definition regex.
    # Known type uses/declarations are accounted separately, not invented features.
    for m in re.finditer(r'\b(?:BASE_FEATURE_WITH_COUNTRY_RESTRICTIONS|BASE_FEATURE|BASE_DECLARE_FEATURE|base::Feature)\b', masked(text)):
        if any(a <= m.start() < b for a, b in covered):
            continue
        tail = text[m.end():text.find('\n', m.end()) if '\n' in text[m.end():] else len(text)]
        if any(a <= m.start() < b for a, b in preprocess):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'macro_template'})
        elif re.match(r'\s*(?:[>*;]|::|[&*]?\s*[,)>]|[&*]\s*\{|[&*]\s*\w+\s*[,)>]|(?:constexpr|const)\s*\*)', tail) or re.fullmatch(r'\s*(?:[A-Z_]+\s+)?\w+\s*;?\s*', tail):
            declarations.append({'line': text.count('\n', 0, m.start()) + 1, 'reason': 'feature_type_use'})
        else:
            end = text.find('\n', m.end())
            add('base_feature', 'unresolved-line-' + str(text.count('\n', 0, m.start()) + 1), m.start(), end if end >= 0 else len(text))
    return [c for c in candidates if not impossible_conditions(c.conditions)], declarations, diagnostics


def parse_mojom(path, original, missing_default_disabled=False):
    text = strip_comments(original)
    module = re.search(r'\bmodule\s+([\w.]+)\s*;', masked(text))
    candidates = []
    for match in re.finditer(r'(\[[^\]]*\]\s*)?\bfeature\s+(\w+)\s*\{', masked(text)):
        opening = text.index('{', match.start())
        closing = matching(text, opening)
        end = closing + 1 if closing is not None else len(text)
        body = text[opening + 1:closing] if closing is not None else ''
        name = re.search(r'\bconst\s+string\s+name\s*=\s*("(?:\\.|[^"\\])*")\s*;', body)
        defaults = list(re.finditer(r'(\[[^\]]*\]\s*)?const\s+bool\s+default_state\s*=\s*(true|false)\s*;', body))
        outer = text[match.start():text.index('feature', match.start())].strip()
        for default in defaults or [None]:
            valid = bool(module and name and (default or missing_default_disabled) and closing is not None)
            conditions = [v for v in (outer, default[1].strip() if default and default[1] else '') if v]
            candidates.append(Candidate('base_feature', match[2], path, text.count('\n', 0, match.start()) + 1,
                text.count('\n', 0, end) + 1, safe_excerpt(text[match.start():end], None), conditions=conditions,
                parsed=valid, value=literal(name[1]) if name else None,
                default='base::FEATURE_' + ('ENABLED' if default and default[2] == 'true' else 'DISABLED') + '_BY_DEFAULT' if default or missing_default_disabled else None,
                namespace=module[1].replace('.', '::') if module else ''))
    return candidates, [], []


def auxiliary_definitions(text):
    """Minimal initializers for titles, choice tables, variations and parameters."""
    text = strip_comments(text)
    result = {}
    enums = []
    for match in re.finditer(r'\benum\s+(?:class\s+)?(\w+)\s*(?::[^{}]+)?\{', masked(text)):
        start = text.index('{', match.start())
        end = matching(text, start)
        if end is not None:
            enums.append((match, start, end))
    spans = []
    for match in re.finditer(r'\bnamespace\s+([\w:]+)\s*\{', masked(text)):
        end = matching(text, text.index('{', match.start()))
        if end is not None:
            spans.append((match.start(), end, match[1]))
    def put(symbol, offset, expr, refs=None):
        symbol = re.sub(r'\s*::\s*', '::', symbol)
        namespace = '::'.join(name for start, end, name in spans if start < offset < end)
        if '::' in symbol:
            prefix, symbol = symbol.rsplit('::', 1)
            namespace = '::'.join(filter(None, (namespace, prefix)))
        result.setdefault(symbol, []).append({'namespace': namespace, 'expression': safe_excerpt(expr, None), 'value': literal(expr),
            'refs': references(expr) if refs is None else refs, 'path_line': text.count('\n', 0, offset) + 1})

    for m in re.finditer(r'\b((?:[A-Za-z_]\w*\s*::\s*)*k[A-Z]\w*)\s*(?:\[[^\]]*\])?\s*(?==|\{)', masked(text)):
        if any(start < m.start() < end for _, start, end in enums):
            continue  # Enumerators end at commas, not the enum's final semicolon.
        start = m.end()
        if text[start] == '=':
            start += 1
        while start < len(text) and text[start].isspace():
            start += 1
        if start >= len(text):
            continue
        end = matching(text, start) if text[start] == '{' else text.find(';', start)
        if end is None or end < 0:
            continue
        expr = text[start:end + (text[start] == '{')].strip()
        put(m[1], m.start(), expr)
    # Braced FeatureParam constants and the corresponding upstream macro.
    for m in re.finditer(r'\b(?:constexpr|const)\s+(?:base::)?FeatureParam\s*<[^;{}]+>\s+(k[A-Z]\w*)\s*\{', masked(text)):
        start = text.index('{', m.start())
        end = matching(text, start)
        if end is not None:
            put(m[1], m.start(), text[start:end + 1])
    for m in re.finditer(r'\bBASE_FEATURE_PARAM\s*\(', masked(text)):
        start = text.index('(', m.start())
        end = matching(text, start)
        args = arguments(text[start + 1:end]) if end is not None else []
        if len(args) >= 4 and re.fullmatch(r'k[A-Z]\w*', args[1]):
            put(args[1], m.start(), text[m.start():end + 1], references(','.join(args[2:])))
    for m, start, end in enums:
        scoped = bool(re.match(r'enum\s+class\b', m[0]))
        base, increment = '0', 0
        for member in arguments(text[start + 1:end]):
            name = re.match(r'(k[A-Z]\w*)\b', member)
            assignment = member.partition('=')
            if assignment[1]:
                base, increment = assignment[2].strip(), 0
            expression = base if not increment else '(' + base + ') + ' + str(increment)
            if name:
                put((m[1] + '::' if scoped else '') + name[1], m.start(), expression)
            increment += 1
    return result


def feature_state_definitions(text):
    """Local non-k state constants and object macros, resolved on demand.

    This does not evaluate arbitrary C++ expressions. The collector accepts
    only literal states/strings or recursively resolved constant identifiers.
    """
    text = strip_comments(text)
    result = {}
    patterns = [(r'\b(?:constexpr|const)\s+(?:(?:base::)?FeatureState|auto)\s+(' + IDENT + r')\s*=\s*([^;]+);', False),
                (r'^\s*#\s*define[ \t]+([A-Za-z_]\w*)[ \t]+([^\n]*(?:\\\n[^\n]*)*)', True)]
    for pattern, macro in patterns:
        for match in re.finditer(pattern, text, re.M):
            name = match[1]
            namespace = '' if macro else namespace_at(text, match.start())
            if '::' in name:
                prefix, name = name.rsplit('::', 1)
                namespace = '::'.join(filter(None, (namespace, prefix)))
            result.setdefault(name, []).append(dict(namespace=namespace, expression=safe_excerpt(match[2].replace('\\\n', ' '), None),
                path_line=text.count('\n', 0, match.start()) + 1, macro=macro))
    return result
