"""Read committed daily collection results for the board, not the newsletter."""
from collections import defaultdict
import json
import subprocess

from pipeline import browser_status, daily_status
from pipeline.reporting.newsletter import (
    CHANNELS, PENDING_TITLE, question_for, read, read_if_present, safe_url, short_title,
)
from pipeline.run_daily import git


def published_features(root, rel, effects, catalogs):
    """Read feature facts at the first commit that published each receipt effect.

    A source revision can be reused by later enrichment. Its observation date and
    the current catalog cannot date a feature fact. Walk all merge parents, not
    commit timestamps or only the main branch's merge commits.
    """
    if not effects:
        return {}
    try:
        if git(root, 'rev-parse', '--is-shallow-repository') != 'false':
            raise ValueError('Daily board needs full Git history; fetch with --unshallow')
        commits = git(root, 'log', '--reverse', '--topo-order', '--full-history',
                      '--format=%H', 'HEAD', '--', rel).splitlines()
        pending = {browser_status.effect_key(e): e for e in effects}
        found = {}
        for commit in commits:
            if not git(root, 'ls-tree', commit, '--', rel):
                continue
            detail = json.loads(git(root, 'show', f'{commit}:{rel}'))
            browser_status.validate_detail(rel, detail)
            for outcome in detail['browsers'].values():
                for effect in outcome.get('effects', []):
                    key = browser_status.effect_key(effect)
                    if key not in pending:
                        continue
                    if effect != pending[key]:
                        raise ValueError('Published daily effect changed: ' + str(key))
                    blob = git(root, 'rev-parse', f'{commit}:{browser_status.CATALOG}')
                    if blob not in catalogs:
                        catalogs[blob] = {f['feature_id']: f for f in json.loads(git(root, 'show', blob))}
                    found[key] = catalogs[blob][effect['feature_id']]
                    del pending[key]
            if not pending:
                return found
    except (subprocess.CalledProcessError, KeyError) as error:
        raise ValueError('Daily board cannot read published feature history: ' + rel) from error
    raise ValueError('Daily board has effects without publication history: ' + rel)


def effect_facts(feature, effect, snapshot):
    """Prefer feature-specific values only for this exact receipt citation."""
    facts = {slot: snapshot.get(slot) for slot in ('version', 'platform', 'channel')}
    for slot, fact in feature.get('feature_facts', {}).items():
        if (fact['source_item_id'], fact['revision_id']) == (effect['item'], effect['revision']):
            facts[slot] = fact['value']
    return facts


def daily_board(root, features, sources):
    """Project one card per saved feature and Korea collection date."""
    feature_map = {f['feature_id']: f for f in features}
    source_map = {s['source_item_id']: s for s in sources}
    titles = read_if_present(root / 'dashboard/daily/titles.json', {})
    statuses, cards, catalogs = {}, [], {}
    for path in sorted((root / daily_status.FOLDER).glob('*.json')):
        receipt = read(path)
        daily_status.validate_receipt(path.relative_to(root).as_posix(), receipt)
        day = receipt['date']
        rel = browser_status.detail_path('daily', receipt['cutoff'])
        detail = browser_status.read_current(root.resolve(), rel)
        statuses[day] = {**receipt, 'has_detail': detail is not None}
        if detail is None:
            continue
        browser_status.check_aggregate(root.resolve(), detail, {})
        browser_status.check_effects(detail, (feature_map, source_map))
        published = published_features(root, rel, [e for outcome in detail['browsers'].values()
                                                 for e in outcome.get('effects', [])], catalogs)
        effects_by_feature = defaultdict(list)
        for outcome in detail['browsers'].values():
            for effect in outcome.get('effects', []):
                effects_by_feature[effect['feature_id']].append(effect)
        for feature_id, effects in sorted(effects_by_feature.items()):
            frozen = [published[browser_status.effect_key(e)] for e in effects]
            feature = frozen[0]
            snapshots = [
                next(r for r in source_map[e['item']]['revisions'] if r['revision_id'] == e['revision'])
                for e in effects
            ]
            urls = sorted({url for r in snapshots if (url := safe_url(r.get('evidence', {}).get('url')))})
            if not urls:
                raise ValueError('Missing official URL for saved daily feature: ' + feature_id)
            changed = any(e['changed'] for e in effects)
            facts = [effect_facts(f, e, r) for f, e, r in zip(frozen, effects, snapshots)]
            versions = sorted({r['version'] for r in facts if r.get('version')})
            platforms = sorted({p for r in facts for p in (r.get('platform') or []) if p != 'unknown'})
            stages = sorted({CHANNELS[r['channel']] for r in facts if r.get('channel') in CHANNELS})
            rollouts = sorted({r['rollout_status'] for r in facts if r.get('rollout_status')})
            original = feature['title']
            title = short_title(feature_id, [original], titles, {})
            excerpts = list(dict.fromkeys(browser_status.displayed_excerpt(f, r) for f, r in zip(frozen, snapshots)))
            card = dict(
                id=f'daily-{day}-{feature_id}', browser=feature['browser'], day=day, title=title,
                title_id=feature_id, original=original, brief=original, stage=' / '.join(stages) or '단계 미확인',
                version=' / '.join(versions) or '미확인', platform=platforms or ['플랫폼 미확인'],
                targets={}, builds='', announced=None, effective=None,
                delta=' · '.join(filter(None, excerpts)), device_test='실기 확인 기록 없음',
                condition='공식 자료에서 확인했습니다. 실제 설치본의 적용 여부는 확인하지 않았습니다.',
                sources=urls, record=rel, media=[], featured=False, title_pending=title == PENDING_TITLE,
                collection_kind='기능 변경' if changed else '근거 보강',
            )
            if rollouts:
                card['condition'] += ' 배포 상태: ' + ' / '.join(rollouts) + '.'
            card['question'] = question_for(card, None)
            cards.append(card)
    return statuses, cards
