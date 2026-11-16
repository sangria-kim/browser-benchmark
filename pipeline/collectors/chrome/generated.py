"""Source-defined Blink generated base features; never claim built output exists."""
import json
import re

from .parser import Candidate, strip_comments, masked, safe_excerpt
from .parser import arguments, literal, matching, conditions_at

INPUT = 'third_party/blink/renderer/platform/runtime_enabled_features.json5'
GENERATOR = 'third_party/blink/renderer/build/scripts/make_runtime_features.py'
TEMPLATE = 'third_party/blink/renderer/build/scripts/templates/features_generated.cc.tmpl'
PATHS = (INPUT, GENERATOR, TEMPLATE)
NETWORK_LIST = 'components/network_session_configurator/common/network_switch_list.h'
NETWORK_DEFINITION = 'components/network_session_configurator/common/network_switches.cc'
MOJO_GENERATOR = 'mojo/public/tools/bindings/generators/mojom_cpp_generator.py'


def mojo_missing_default_is_disabled(files):
    generator = files.get(MOJO_GENERATOR, '')
    function = re.search(r'  def _IsFeatureOnByDefault\(self, kind\):(.*?)(?=\n  def )', generator, re.S)
    return bool(function and 'if constant.name == "default_state":\n        return constant.value == "true"\n    return False' in function[1])


def network_switches(files):
    if NETWORK_LIST not in files:
        return [], []
    definition = files.get(NETWORK_DEFINITION, '')
    if '#define NETWORK_SWITCH(name, value) const char name[] = value;' not in definition or ('#include "' + NETWORK_LIST + '"') not in definition:
        return [], ['unsupported_network_switch_generator']
    text = strip_comments(files[NETWORK_LIST])
    candidates = []
    for match in re.finditer(r'\bNETWORK_SWITCH\s*\(', masked(text)):
        opening = text.index('(', match.start())
        closing = matching(text, opening)
        args = arguments(text[opening + 1:closing]) if closing is not None else []
        valid = len(args) == 2 and re.fullmatch(r'k[A-Z]\w*', args[0]) and literal(args[1]) is not None
        symbol = args[0] if args else 'unresolved-network-switch'
        candidates.append(Candidate('command_switch', symbol, NETWORK_LIST, text.count('\n', 0, match.start()) + 1,
            text.count('\n', 0, closing or opening) + 1, 'const char ' + symbol + '[] = ' + args[1] + ';' if valid else safe_excerpt(text[match.start():closing], None),
            conditions=conditions_at(text, match.start()), parsed=bool(valid), value=literal(args[1]) if valid else None, namespace='switches'))
    return candidates, []


def json5_subset(text):
    """Only JSON plus comments, identifier keys and trailing commas."""
    text = strip_comments(text)
    edits = []
    clean = masked(text)
    for match in re.finditer(r'(?<=[{,])\s*(\w+)\s*:', clean):
        edits.append((match.start(1), match.end(1), json.dumps(match[1])))
    for match in re.finditer(r',\s*(?=[}\]])', text):
        if clean[match.start()] == ',':
            edits.append((match.start(), match.start() + 1, ''))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return json.loads(text)


def blink_features(files):
    if not any(p in files for p in PATHS):
        return [], []
    if not all(p in files for p in PATHS):
        return [], ['missing_blink_generator_inputs']
    source, generator, template = (files[p] for p in PATHS)
    # These are explicit upstream rules. Unsupported generator changes fail
    # closed instead of guessing from a runtime feature's name.
    required = ["if feature['base_feature'] == 'none':", "elif feature['base_feature'] == '':",
                "feature['base_feature'] = feature['name']"]
    if not all(v in generator for v in required) or not all(v in template for v in (
            'BASE_FEATURE(k{{feature.base_feature}}', "feature.base_feature_status == 'enabled'",
            "feature.status == 'stable'", "feature.status[platform] == 'stable'")):
        return [], ['unsupported_blink_generator_rules']
    try:
        data = json5_subset(source)
        clean_source = strip_comments(source)
        if data['parameters']['base_feature']['default'] != '' or data['parameters']['base_feature_status']['default'] != '':
            raise ValueError('Changed generator defaults')
        candidates = []
        for row in data['data']:
            name = row.get('base_feature') or row['name']
            if name == 'none':
                continue
            if not re.fullmatch(r'[A-Za-z_]\w*', name):
                raise ValueError('Unsupported generated symbol')
            override = row.get('base_feature_status')
            status = row.get('status', '')
            if override:
                if override not in ('enabled', 'disabled'):
                    raise ValueError('Unsupported generated default')
                default = 'base::FEATURE_' + override.upper() + '_BY_DEFAULT'
            elif isinstance(status, str):
                default = 'base::FEATURE_' + ('ENABLED' if status == 'stable' else 'DISABLED') + '_BY_DEFAULT'
            elif isinstance(status, dict):
                if set(status) - set(data['parameters']['status']['valid_keys']) - {'default'}:
                    raise ValueError('Unsupported generated platform')
                default = json.dumps({k: 'base::FEATURE_' + ('ENABLED' if v == 'stable' else 'DISABLED') + '_BY_DEFAULT'
                                      for k, v in {'default': '', **status}.items()}, sort_keys=True)
            else:
                raise ValueError('Unsupported generated status')
            match = re.search(r'(?:\bname|"name")\s*:\s*' + re.escape(json.dumps(row['name'])), clean_source)
            if not match:
                raise ValueError('Generated input location missing')
            line = source.count('\n', 0, match.start()) + 1
            candidates.append(Candidate('base_feature', 'k' + name, INPUT, line, line,
                'Generated BASE_FEATURE(k' + name + ', ' + default + ')', parsed=True,
                value=name, default=default, namespace='blink::features'))
        return candidates, []
    except (ValueError, KeyError, TypeError):
        return [], ['unsupported_blink_runtime_definition']
