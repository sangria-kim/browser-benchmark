"""Chrome Releases Blogger byline evidence and the daily collection boundary."""
import contextlib
import hashlib
from io import StringIO
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline.collectors.browser import Response
from pipeline.collectors.browser.html import Tree, blocks, boundary


ROOT = Path(__file__).resolve().parents[1]
HOME = 'https://chromereleases.googleblog.com/'
URL = HOME + '2026/11/test.html'
PROFILE = '<meta itemprop="url" content="https://plus.google.com/116899029375914044550">'


def author(fields=PROFILE):
    return '<span itemprop="author" itemscope itemtype="http://schema.org/Person">' + fields + '</span>'


def document(line, publisher='Google Chrome', card=None, product='<p id="tabs">Pin tabs.</p>'):
    if card is None:
        card = author()
    return ('<meta property="article:published_time" content="2026-11-10">'
            '<div class="post-body"><div class="post-content"><script type="text/template">'
            + product + line + '<p>' + publisher + '</p>' + card + '</script></div></div>')


def units(markup, reviewed=(), url=URL):
    return blocks(boundary(Tree(markup).root, 'chrome-releases', reviewed, document_url=url))


class SignoffTests(unittest.TestCase):
    def test_marker_remains_private_and_is_never_a_product(self):
        for card, line in [
            (author(), 'Chrome Release Team'),
            (author('<meta itemprop="name" content="Example Publisher">'), 'Example Publisher'),
            (author('<meta itemprop="name" content="Example Publisher">'), '<span>Example</span> <b>Publisher</b>'),
        ]:
            with self.subTest(line=line):
                rows = units(document('<p>' + line + '</p>', card=card))
                self.assertEqual([('tabs', 'Pin tabs.')], [(r['key'], r['text']) for r in rows])
        text = '<p>Reviewed Example</p>'
        rows = units(document(text, card=author('')), [hashlib.sha256(b'Reviewed Example').hexdigest()])
        self.assertEqual(['tabs'], [r['key'] for r in rows])

    def test_explicit_long_author_name_preserves_anchored_or_linked_product_units(self):
        name = 'Example Editorial Contributor for Browser Interface and Release Documentation'
        card = author(f'<meta itemprop="name" content="{name}">')
        self.assertGreater(len(name), 64)
        self.assertEqual(['tabs'], [r['key'] for r in units(document(f'<p>{name}</p>', card=card))])
        for row in [f'<p id="changes">{name}</p>', f'<p><a href="/release">{name}</a></p>']:
            self.assertEqual(name, units(document(row, card=card))[-1]['text'])

    def test_unknown_short_lines_and_insufficient_author_evidence_stay_unresolved(self):
        for line, card, publisher in [
            ('Pin tabs.', author(), 'Google Chrome'),
            ('<span>Pin</span> <em>tabs.</em>', author(), 'Google Chrome'),
            ('<span>Chrome</span><b>Release Team</b>', author(), 'Google Chrome'),
            ('Chrome Release Team', '', 'Google Chrome'),
            ('Chrome Release Team', author(''), 'Google Chrome'),
            ('Chrome Release Team', author(PROFILE.replace('116899029375914044550', '123')), 'Google Chrome'),
            ('Chrome Release Team', author() + '<footer>Another author</footer>', 'Google Chrome'),
            ('Chrome Release Team', '<div>' + author() + '</div>', 'Google Chrome'),
            ('Chrome Release Team', author() + author(), 'Google Chrome'),
            ('Chrome Release Team', author(PROFILE + '<meta itemprop="name" content="Other Team">'), 'Google Chrome'),
            ('Chrome Release Team', author(), 'Google ChromeOS'),
        ]:
            with self.subTest(line=line, card=card, publisher=publisher):
                rows = units(document('<p>' + line + '</p>', publisher, card))
                self.assertEqual([('tabs', True), ('chrome-post-signoff', False)],
                                 [(r['key'], r['parsed']) for r in rows])

    def test_template_review_survives_page_footer_change_and_expires_on_article_change(self):
        markup = document('<p>Example Editor</p>', publisher='Google ChromeOS')
        markup = markup.replace('<p id="tabs">', '<div>' + author('') + '</div><p id="tabs">')
        template = next(n for n in Tree(markup).root.walk() if n.tag == 'script')
        reviewed = hashlib.sha256(''.join(template.children).encode()).hexdigest()
        with patch('pipeline.collectors.browser.html.REVIEWED_CHROME_TEMPLATES', {URL: reviewed}):
            self.assertFalse(units(markup, url=HOME + '2026/11/copied.html')[-1]['parsed'])
            self.assertEqual(['tabs'], [r['key'] for r in units(markup + '<footer>Later</footer>')])
            for edited in [markup.replace('Pin tabs.', 'Share tabs.'), markup.replace('Editor', 'Changed')]:
                self.assertEqual(('chrome-post-signoff', False),
                                 (units(edited)[-1]['key'], units(edited)[-1]['parsed']))

    def test_only_the_terminal_signature_can_be_removed(self):
        product = '<p id="first">Chrome Release Team</p><p id="second"><em>Pin tabs.</em></p>'
        rows = units(document('<p>Chrome Release Team</p>', product=product))
        self.assertEqual([('first', 'Chrome Release Team'), ('second', 'Pin tabs.')],
                         [(r['key'], r['text']) for r in rows])
        rows = units(document('<ul><li id="feature">Chrome Release Team</li></ul>'))
        self.assertEqual('Chrome Release Team', rows[-1]['text'])
        product = document('<p id="before">Pin tabs.</p>').replace('<p>Google Chrome</p>',
                                                                  '<ul><li id="last">Google Chrome</li></ul>')
        self.assertEqual(['tabs', 'before', 'last'], [r['key'] for r in units(product)])

    def test_daily_cli_keeps_product_identity_and_reopens_changed_unreviewed_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / 'repo'
            shutil.copytree(ROOT / 'config', repo / 'config')
            pages = {HOME: '<h2><a href="' + URL + '">Update</a></h2>'}
            prior = None
            for run, line, code, extra in [
                ('proved', '<p>Chrome Release Team</p>', 0, {}),
                ('ambiguous', '<p>Pin new tabs.</p>', 2, {}),
                ('anchored', '<p id="share-tabs">Share tabs.</p>', 0, {'share-tabs': 'Share tabs.'}),
                ('same-label', '<p id="release-team">Chrome Release Team</p>', 0,
                 {'release-team': 'Chrome Release Team'}),
                ('publisher-link', '<p id="real-change">Pin more tabs.</p>', 0,
                 {'real-change': 'Pin more tabs.', 'document:p:3': 'Google Chrome'}),
                ('publisher-anchor', '<p id="share-tabs">Share tabs.</p>', 0,
                 {'share-tabs': 'Share tabs.', 'new-search-feature': 'Google Chrome'}),
            ]:
                pages[URL] = document(line)
                if run == 'publisher-link':
                    pages[URL] = pages[URL].replace('<p>Google Chrome</p>',
                        '<p><a href="https://developer.chrome.com/docs/capabilities/web-apis">Google Chrome</a></p>')
                if run == 'publisher-anchor':
                    pages[URL] = pages[URL].replace('<p>Google Chrome</p>',
                        '<p id="new-search-feature"><a href="/new-feature">Google Chrome</a></p>')

                def request(url):
                    return Response(url, pages[url].encode())

                argv = ['pipeline.run_daily', '--repository', str(repo), '--private-dir', str(root / 'runs'),
                        '--mode', 'daily', '--daily-status', '--run-id', run, '--source', 'chrome-releases',
                        '--cutoff', '2026-11-25T07:00:00+09:00']
                with patch('sys.argv', argv), patch('pipeline.collectors.browser.collector.HTTPTransport',
                                                     return_value=request):
                    with contextlib.redirect_stdout(StringIO()), self.assertRaises(SystemExit) as exit_status:
                        runpy.run_path(str(ROOT / 'pipeline/run_daily.py'), run_name='__main__')
                work = root / 'runs' / run / 'work'
                state = json.loads((work / 'browser/chrome-releases.json').read_text())
                self.assertEqual(code, exit_status.exception.code, state)
                self.assertEqual(int(code != 0), state['unparsed'])
                rows = json.loads((work / 'candidates/chrome-releases.json').read_text())
                self.assertEqual({'tabs': 'Pin tabs.', **extra}, {r['item_key']: r['title'] for r in rows})
                row, = [r for r in rows if r['item_key'] == 'tabs']
                self.assertEqual(('tabs', 'Pin tabs.'), (row['item_key'], row['title']))
                identity = row['source_item_id'], row['item_content_sha256']
                if prior:
                    self.assertEqual(prior, identity)
                prior = identity
                self.assertFalse((repo / 'data/daily-status').exists())
                if code:
                    self.assertFalse(json.loads((work.parent / 'feature-run.json').read_text())['complete'])
