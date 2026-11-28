import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase

from pipeline import browser_status, daily_status
from pipeline.normalize.storage import load_source_items
from scripts.build_daily_dashboard import write_home
from scripts.dashboard_collection import daily_board, effect_facts


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


class NovemberCollectionTests(TestCase):
    # Pin the reviewed records. Later completion of these incomplete runs is
    # valid and must not silently replace the regression inputs.
    RECORDS_COMMIT = '27d047b51faa0ed59972096edf075e88a12fda2b'

    @classmethod
    def setUpClass(cls):
        temp = TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name) / 'records'
        subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(ROOT), str(cls.root)],
                       check=True, capture_output=True)

        def git(*args):
            return subprocess.check_output(['git', '-C', str(cls.root), *args], stderr=subprocess.PIPE)

        git('reset', '--soft', cls.RECORDS_COMMIT)
        paths = {browser_status.CATALOG, 'dashboard/daily/titles.json'}
        for day in ('2026-11-27', '2026-11-28'):
            rel = browser_status.detail_path('daily', day + 'T07:00:00+09:00')
            paths.update([rel, f'{daily_status.FOLDER}/{day}.json'])
            detail = json.loads(git('show', f'HEAD:{rel}'))
            for browser, outcome in detail['browsers'].items():
                paths.update(f"data/source-items/{browser}/{e['source_id']}.json"
                             for e in outcome.get('effects', []))
        git('restore', '--source=HEAD', '--staged', '--worktree', '--', *sorted(paths))
        cls.features = json.loads((cls.root / browser_status.CATALOG).read_text())
        cls.sources = load_source_items(cls.root)
        cls.statuses, cls.cards = daily_board(cls.root, cls.features, cls.sources)

    def test_november_28_all_five_edge_cards_have_confirmed_scope(self):
        cards = [c for c in self.cards if c['day'] == '2026-11-28']
        self.assertEqual(8, len(cards))
        self.assertEqual(3, sum(c['collection_kind'] == '기능 변경' for c in cards))
        edge = [c for c in cards if c['browser'] == 'edge']
        self.assertEqual(5, len(edge))
        self.assertTrue(all(c['collection_kind'] == '근거 보강' for c in edge))
        self.assertTrue(all(c['version'] != '미확인' and c['stage'] != '단계 미확인' for c in edge))
        apple = next(c for c in edge if c['title_id'] == 'feature-ef52f67914e35fd5b3a96416')
        self.assertEqual(('158.0.4370.33', ['Android', 'iOS'], '정식판'),
                         (apple['version'], apple['platform'], apple['stage']))
        beta = next(c for c in edge if c['title_id'] == 'feature-52978585e8f80e3de853dad5')
        self.assertEqual(('159.0.4402.7', '베타', ['플랫폼 미확인']),
                         (beta['version'], beta['stage'], beta['platform']))
        self.assertIn('배포 상태: gradual.', beta['condition'])
        self.assertTrue(all(c['stage'] != '정식판' for c in cards if c['browser'] == 'chrome'))

    def test_november_27_preserves_changes_enrichment_and_unknown_slots(self):
        cards = [c for c in self.cards if c['day'] == '2026-11-27']
        self.assertEqual(12, len(cards))
        self.assertEqual(5, sum(c['collection_kind'] == '기능 변경' for c in cards))
        self.assertEqual(7, sum(c['collection_kind'] == '근거 보강' for c in cards))
        whale = [c for c in cards if c['browser'] == 'whale']
        self.assertEqual(3, len(whale))
        self.assertTrue(all((c['version'], c['platform'], c['stage']) ==
                            ('4.1', ['iOS'], '단계 미확인') for c in whale))
        tunnel = next(c for c in cards if c['title_id'] == 'feature-57a41b890977b77f9452fe77')
        self.assertEqual(('157.0.4341.42', ['iOS'], '정식판'),
                         (tunnel['version'], tunnel['platform'], tunnel['stage']))

    def test_actual_incomplete_days_and_confirmed_zero_browsers(self):
        for day in ('2026-11-27', '2026-11-28'):
            with self.subTest(day=day):
                status = self.statuses[day]
                self.assertEqual(('incomplete', None, None),
                                 (status['status'], status['change_count'], status['collected_feature_count']))
                detail = browser_status.read_current(self.root, browser_status.detail_path('daily', status['cutoff']))
                self.assertEqual(('complete', 0, 0), tuple(detail['browsers']['safari'][k]
                                 for k in ('status', 'change_count', 'collected_feature_count')))
                self.assertEqual(('incomplete', None), tuple(detail['browsers']['firefox'][k]
                                 for k in ('status', 'change_count')))
        edge = detail['browsers']['edge']
        self.assertEqual(('complete', 0, 5), (edge['status'], edge['change_count'], edge['collected_feature_count']))

    def test_later_catalog_enrichment_cannot_change_actual_cards(self):
        features = deepcopy(self.features)
        for feature in features:
            # Reuse a pinned revision, including its old observed_at. A revision
            # or cutoff filter alone would leak these later values into cards.
            if not feature.get('source_revision_ids'):
                continue
            ident, revisions = next(iter(feature['source_revision_ids'].items()))
            feature['feature_facts'] = {slot: dict(value=value, source_item_id=ident, revision_id=revisions[0])
                                       for slot, value in [('version', '999.0'), ('platform', ['FutureOS']),
                                                           ('channel', 'nightly'), ('rollout_status', 'future')]}
        statuses, cards = daily_board(self.root, features, self.sources)
        self.assertEqual(self.statuses, statuses)
        self.assertEqual(self.cards, cards)


class PublicationHistoryTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Board test')
        self.git('config', 'user.email', 'board@example.invalid')
        self.git('commit', '--allow-empty', '-m', 'Before collection')
        self.git('switch', '-c', 'collection')
        self.snapshot = dict(revision_id='rev-1', evidence=dict(url='https://example.com/release', excerpt='Feature'),
                             version=None, channel=None, platform=['unknown'])
        self.source = dict(source_item_id='src-1', source_id='edge-stable', browser='edge', revisions=[self.snapshot])
        self.feature = dict(feature_id='feature-1', browser='edge', title='Original feature', source_item_ids=['src-1'],
                            source_revision_ids={'src-1': ['rev-1']}, feature_facts={})
        self.effect = dict(feature_id='feature-1', source_id='edge-stable', item='src-1', revision='rev-1',
                           snapshot=browser_status.value_hash(self.snapshot), quote=None, changed=True)
        self.save_day('2026-11-27')
        self.commit('Initial collection without facts')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE).decode().strip()

    def write(self, rel, value):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def commit(self, message):
        self.write(browser_status.CATALOG, [self.feature])
        self.git('add', '.')
        self.git('commit', '-m', message)

    def save_day(self, day):
        cutoff = day + 'T07:00:00+09:00'
        rel, receipt = daily_status.receipt(cutoff, int(self.effect['changed']), 1)
        self.write(rel, receipt)
        scope = dict(mode='daily', cutoff=datetime.fromisoformat(cutoff).astimezone(timezone.utc).isoformat(),
                     start='2026-10-28T22:00:00+00:00',
                     origin='daily', registry='0' * 64, expected={'edge': ['edge-stable']})
        detail = browser_status.initial(scope)
        detail['browsers']['edge'] = dict(status='complete', classification='0' * 64,
                                         effects=[deepcopy(self.effect)], change_count=int(self.effect['changed']),
                                         collected_feature_count=1)
        self.write(browser_status.detail_path('daily', cutoff), browser_status.seal(detail))

    def board(self):
        return daily_board(self.root, [self.feature], [self.source])

    def enrich(self):
        self.feature['feature_facts'] = {slot: dict(value=value, source_item_id='src-1', revision_id='rev-1')
                                        for slot, value in [('version', '158.0'), ('platform', ['Android']),
                                                            ('channel', 'stable')]}
        self.effect['changed'] = False
        self.save_day('2026-11-28')
        self.commit('Enrich the same source revision on the next day')

    def test_same_revision_enrichment_and_merge_keep_old_card_fixed(self):
        before = self.board()[1][0]
        self.enrich()
        self.git('switch', 'main')
        self.git('merge', '--no-ff', 'collection', '-m', 'Merge both collection days')
        cards = self.board()[1]
        self.assertEqual(before, cards[0])
        self.assertEqual('미확인', cards[0]['version'])
        self.assertEqual(('158.0', ['Android'], '정식판', '근거 보강'),
                         tuple(cards[1][k] for k in ('version', 'platform', 'stage', 'collection_kind')))
        # Later changes to the source head and to the title also stay out.
        later = dict(self.snapshot, revision_id='rev-2', version='999', channel='nightly', platform=['FutureOS'])
        self.source['revisions'].append(later)
        self.source.update(version='999', channel='nightly', platform=['FutureOS'])
        self.feature['title'] = 'Later catalog title'
        self.commit('Later catalog change without receipt change')
        self.assertEqual(cards, self.board()[1])

    def test_uncommitted_effect_fails_instead_of_using_latest_catalog(self):
        self.effect['changed'] = False
        self.save_day('2026-11-28')
        with self.assertRaisesRegex(ValueError, 'without publication history'):
            self.board()

    def test_shallow_history_fails_even_when_head_contains_facts(self):
        self.enrich()
        target = Path(self.temp.name) / 'shallow'
        subprocess.run(['git', 'clone', '--depth=1', self.root.as_uri(), str(target)],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, 'full Git history'):
            daily_board(target, [self.feature], [self.source])

    def test_missing_git_history_fails_instead_of_backfilling(self):
        (self.root / '.git').rename(Path(self.temp.name) / 'saved-git')
        with self.assertRaisesRegex(ValueError, 'cannot read published feature history'):
            self.board()

    def test_fact_precedence_requires_both_citation_parts(self):
        snapshot = dict(version='source-version', platform=['Windows'], channel='beta')
        for item, revision, expected in [('src-1', 'rev-1', 'feature-version'),
                                         ('src-other', 'rev-1', 'source-version'),
                                         ('src-1', 'rev-other', 'source-version')]:
            with self.subTest(item=item, revision=revision):
                feature = dict(feature_facts={'version': dict(value='feature-version',
                               source_item_id=item, revision_id=revision)})
                self.assertEqual(dict(version=expected, platform=['Windows'], channel='beta'),
                                 effect_facts(feature, self.effect, snapshot))

    def test_features_on_one_source_page_keep_independent_facts(self):
        second = deepcopy(self.feature)
        second['feature_id'] = 'feature-2'
        second['feature_facts'] = {'version': dict(value='999', source_item_id='src-1', revision_id='rev-1')}
        self.save_day('2026-11-28')
        rel = browser_status.detail_path('daily', '2026-11-28T07:00:00+09:00')
        detail = json.loads((self.root / rel).read_text())
        detail['browsers']['edge']['effects'].append(dict(self.effect, feature_id='feature-2'))
        detail['browsers']['edge'].update(change_count=2, collected_feature_count=2)
        self.write(rel, browser_status.seal(detail))
        self.write(*daily_status.receipt('2026-11-28T07:00:00+09:00', 2, 2))
        self.write(browser_status.CATALOG, [self.feature, second])
        self.git('add', '.')
        self.git('commit', '-m', 'Two features on one shared page')
        cards = daily_board(self.root, [self.feature, second], [self.source])[1]
        cards = {c['title_id']: c for c in cards if c['day'] == '2026-11-28'}
        self.assertEqual('미확인', cards['feature-1']['version'])
        self.assertEqual('999', cards['feature-2']['version'])

    def test_multiple_citations_do_not_add_unknown_to_a_confirmed_channel(self):
        self.enrich()
        other = dict(self.snapshot, revision_id='rev-2')
        self.source['revisions'].append(other)
        self.feature['source_revision_ids']['src-1'].append('rev-2')
        self.save_day('2026-11-29')
        rel = browser_status.detail_path('daily', '2026-11-29T07:00:00+09:00')
        detail = json.loads((self.root / rel).read_text())
        detail['browsers']['edge']['effects'].append(dict(self.effect, revision='rev-2',
                                                         snapshot=browser_status.value_hash(other)))
        self.write(rel, browser_status.seal(detail))
        self.commit('Add another citation with no channel')
        card = self.board()[1][-1]
        self.assertEqual(('158.0', ['Android'], '정식판', '근거 보강'),
                         tuple(card[k] for k in ('version', 'platform', 'stage', 'collection_kind')))
