"""Read committed daily collection results for the board, not the newsletter."""
from collections import defaultdict

from pipeline import browser_status, daily_status
from pipeline.reporting.newsletter import (
    CHANNELS, PENDING_TITLE, question_for, read, read_if_present, safe_url, short_title,
)


def daily_board(root, features, sources):
    """Project one card per saved feature and Korea collection date."""
    feature_map = {f['feature_id']: f for f in features}
    source_map = {s['source_item_id']: s for s in sources}
    titles = read_if_present(root / 'dashboard/daily/titles.json', {})
    statuses, cards = {}, []
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
        effects_by_feature = defaultdict(list)
        for outcome in detail['browsers'].values():
            for effect in outcome.get('effects', []):
                effects_by_feature[effect['feature_id']].append(effect)
        for feature_id, effects in sorted(effects_by_feature.items()):
            feature = feature_map[feature_id]
            snapshots = [
                next(r for r in source_map[e['item']]['revisions'] if r['revision_id'] == e['revision'])
                for e in effects
            ]
            urls = sorted({url for r in snapshots if (url := safe_url(r.get('evidence', {}).get('url')))})
            if not urls:
                raise ValueError('Missing official URL for saved daily feature: ' + feature_id)
            changed = any(e['changed'] for e in effects)
            versions = sorted({r['version'] for r in snapshots if r.get('version')})
            platforms = sorted({p for r in snapshots for p in (r.get('platform') or []) if p != 'unknown'})
            stages = sorted({CHANNELS.get(r.get('channel'), '단계 미확인') for r in snapshots})
            original = feature['title']
            title = short_title(feature_id, [original], titles, {})
            excerpts = list(dict.fromkeys(browser_status.displayed_excerpt(feature, r) for r in snapshots))
            card = dict(
                id=f'daily-{day}-{feature_id}', browser=feature['browser'], day=day, title=title,
                title_id=feature_id, original=original, brief=original, stage=' / '.join(stages),
                version=' / '.join(versions) or '미확인', platform=platforms or ['플랫폼 미확인'],
                targets={}, builds='', announced=None, effective=None,
                delta=' · '.join(filter(None, excerpts)), device_test='실기 확인 기록 없음',
                condition='공식 자료에서 확인했습니다. 실제 설치본의 적용 여부는 확인하지 않았습니다.',
                sources=urls, record=rel, media=[], featured=False, title_pending=title == PENDING_TITLE,
                collection_kind='기능 변경' if changed else '근거 보강',
            )
            card['question'] = question_for(card, None)
            cards.append(card)
    return statuses, cards
