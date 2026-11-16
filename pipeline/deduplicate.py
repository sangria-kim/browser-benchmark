"""Deterministic identities and evidence-backed alias corrections.

No fuzzy title matching. Aliases are lookup links, never destructive merges.
Old catalog/event records remain addressable after a correction.
"""
import hashlib
import json
import re

from schemas.validate import ContractError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def stable_id(prefix, value):
    return prefix + '-' + digest(value)[:24]


def feature_identity(browser, canonical_key):
    return stable_id('feature', [browser, canonical_key])


def event_identity(subject_id, event_type, version, channel, platform, before, after, predecessor=None):
    return stable_id('event', [subject_id, event_type, version, channel, sorted(platform), before, after, predecessor])


class AliasIndex:
    """Append-only corrections. Later revisions can repair a wrong alias.

    Each entry cites public source items. Resolving an alias does not rewrite
    existing records, event owners, source evidence or historical PM judgments.
    """
    def __init__(self, entries=(), subjects=None, source_ids=None):
        self.entries = list(entries)
        self.active = {}
        ids = set()
        for entry in self.entries:
            required = {'alias_id', 'subject_kind', 'old_id', 'target_id', 'source_item_ids', 'reason', 'revision', 'supersedes'}
            if set(entry) != required or entry['subject_kind'] not in ('feature', 'experiment'):
                raise ContractError('Invalid alias correction')
            for field in ('alias_id', 'old_id', 'target_id'):
                if not isinstance(entry[field], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]*', entry[field]):
                    raise ContractError('Invalid alias ID')
            if (not isinstance(entry['reason'], str) or not isinstance(entry['source_item_ids'], list)
                    or any(not isinstance(s, str) for s in entry['source_item_ids'])
                    or len(set(entry['source_item_ids'])) != len(entry['source_item_ids'])
                    or type(entry['revision']) is not int
                    or (entry['supersedes'] is not None and not isinstance(entry['supersedes'], str))):
                raise ContractError('Invalid alias correction types')
            key = (entry['subject_kind'], entry['old_id'])
            prior = self.active.get(key)
            if entry['alias_id'] in ids or not entry['reason'] or not entry['source_item_ids']:
                raise ContractError('Alias needs unique identity and evidence')
            if entry['revision'] != (prior['revision'] + 1 if prior else 1) or entry['supersedes'] != (prior['alias_id'] if prior else None):
                raise ContractError('Alias correction must supersede its previous revision')
            if subjects is not None and entry['target_id'] not in subjects.get(entry['subject_kind'], set()):
                raise ContractError('Missing alias target')
            if source_ids is not None and not set(entry['source_item_ids']).issubset(source_ids):
                raise ContractError('Missing alias evidence')
            ids.add(entry['alias_id'])
            self.active[key] = entry
        for kind, ident in self.active:
            self.resolve(kind, ident)

    def resolve(self, kind, ident):
        visited = set()
        while (kind, ident) in self.active:
            if ident in visited:
                raise ContractError('Alias cycle')
            visited.add(ident)
            ident = self.active[kind, ident]['target_id']
        return ident
