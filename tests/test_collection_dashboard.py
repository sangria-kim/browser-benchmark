import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pipeline import browser_status, daily_status
from pipeline.normalize.storage import load_source_items
from scripts.build_daily_dashboard import write_home
from scripts.dashboard_collection import daily_board


ROOT = Path(__file__).resolve().parents[1]


class DailyBoardTests(TestCase):
    def test_board_shows_saved_features_from_the_morning_run(self):
        day = '2026-11-26'
        cutoff = '2026-11-26T07:00:00+09:00'
        detail = browser_status.read_current(ROOT, browser_status.detail_path('daily', cutoff))
        effects = [e for outcome in detail['browsers'].values() for e in outcome.get('effects', [])]
        ids = {e['feature_id'] for e in effects}
        changed = {e['feature_id'] for e in effects if e['changed']}
        receipt = json.loads((ROOT / daily_status.FOLDER / f'{day}.json').read_text())
        features = json.loads((ROOT / browser_status.CATALOG).read_text())
        payload = dict(events=[], catalog={}, source={'sha': '0' * 40})
        with TemporaryDirectory() as temp:
            output = Path(temp)
            write_home(output, ROOT, payload, [], {}, features=features, sources=load_source_items(ROOT))
            rendered = (output / 'index.html').read_text().split('id="daily-data">')[1].split('</script>')[0]
            data = json.loads(rendered)
        cards = [c for c in data['cards'] if c['day'] == day]
        self.assertEqual(len(ids), len(cards))
        self.assertEqual({f'daily-{day}-{i}' for i in ids}, {c['id'] for c in cards})
        self.assertEqual(len(changed), sum(c['collection_kind'] == '기능 변경' for c in cards))
        self.assertTrue(all(c['sources'] and c['device_test'] == '실기 확인 기록 없음' for c in cards))
        self.assertEqual(receipt, {k: data['daily_status'][day][k] for k in receipt})
        self.assertFalse(any(i['day'] == day for i in data['drafts']))

    def test_same_day_editorial_card_stays_available_only_for_details(self):
        day = '2026-11-26'
        event = json.loads(next((ROOT / 'data/events').glob('*.json')).read_text())
        event.update(event_id='editorial-overlap-fixture', observed_at=f'{day}T09:00:00+09:00',
                     title='독립 뉴스레터 상세 제목', summary='독립 뉴스레터 상세 제목')
        payload = dict(events=[event], catalog={}, source={'sha': '0' * 40})
        features = json.loads((ROOT / browser_status.CATALOG).read_text())
        with TemporaryDirectory() as temp:
            output = Path(temp)
            write_home(output, ROOT, payload, [], {}, features=features, sources=load_source_items(ROOT))
            rendered = (output / 'index.html').read_text().split('id="daily-data">')[1].split('</script>')[0]
            data = json.loads(rendered)
        issue = next(i for i in data['drafts'] if i['day'] == day)
        self.assertEqual([event['event_id']], [s['id'] for s in issue['stories']])
        self.assertNotIn(event['event_id'], [c['id'] for c in data['cards']])
        self.assertEqual([event['event_id']], [c['id'] for c in data['detail_cards']])
        self.assertTrue(all(c['id'].startswith(f'daily-{day}-') for c in data['cards'] if c['day'] == day))

    def test_empty_confirmed_and_incomplete_remain_distinct_without_detail(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for day, counts in [('2026-12-01', (0, 0)), ('2026-12-02', (None, None))]:
                rel, value = daily_status.receipt(f'{day}T07:00:00+09:00', *counts)
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))
            statuses, cards = daily_board(root, [], [])
        self.assertEqual([], cards)
        self.assertEqual(('complete', 0), (statuses['2026-12-01']['status'], statuses['2026-12-01']['change_count']))
        self.assertEqual(('incomplete', None), (statuses['2026-12-02']['status'], statuses['2026-12-02']['change_count']))
        self.assertNotIn('2026-12-03', statuses)
