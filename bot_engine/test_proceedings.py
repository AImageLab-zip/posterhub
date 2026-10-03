import io
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase

from . import paper_search as search
from . import proceedings
from . import utils_ai as ai
from .models import ProceedingsPaper, ProceedingsSource, ResearchPoster

RALMPH = 'RaLMPH: Reliability-Aware Learning for Multi-Pathologist Harmonization in Whole-Slide Image Classification'
RALPH_POSTER = 'RaLPH: Reliability-aware Learning for Multi-Pathologist Harmonization in Whole-Slide Image Classification'
RALMPH_AUTHORS = 'Sungrae Hong, Jiwon Jeong, Seungho Choe, Donghee Han, Mun Yong Yi'
FEDAGREE = 'FedAgree: Label-Free Performance Estimation Under Distribution Shift for Federated Medical Imaging Analysis'
SKIN = 'Skin-R1: Clinical Knowledge-Guided Dermatological Diagnosis Using Vision-Language Models'

CVF_PAGE = '''<dl>
<dt class="ptitle"><br><a href="/content/CVPR2026/html/A_paper.html">Keypoint Correspondence for Object Tracking</a></dt>
<dd><form class="authsearch"><input type="hidden" name="query_author" value="Jie Xiao">
<a href="#">Jie Xiao</a>,</form><form class="authsearch"><a href="#">Yinchao Ma</a></form></dd>
<dd>[<a href="/content/CVPR2026/papers/A_paper.pdf">pdf</a>] [<a href="/supp.pdf">supp</a>]</dd>
<dt class="ptitle"><br><a href="/content/CVPR2026/html/B_paper.html">Another Paper Without Links Below It</a></dt>
</dl>'''

ECVA_PAGE = '''<dl>
<dt class="ptitle"><br><a href=papers/eccv_2024/papers_ECCV/html/4_ECCV_2024_paper.php>
Is Retain Set All You Need in Machine Unlearning?</a></dt>
<dd>Jacopo Bonato*, Marco Cotogni, Luigi Sabetta*</dd>
<dd>[<a href='papers/eccv_2024/papers_ECCV/papers/00004.pdf'>pdf</a>]</dd>
<dt class="ptitle"><br><a href=papers/eccv_2022/papers_ECCV/html/9_ECCV_2022_paper.php>
An Older ECCV Paper From Another Year</a></dt>
<dd>Someone Else</dd>
</dl>'''


def source(parser, url='https://example.org/list', **options):
    return ProceedingsSource(conference='X', year=2026, url=url, parser=parser, options=options)


def parse(parser, body, **kwargs):
    return proceedings.PARSERS[parser](body.encode(), source(parser, **kwargs))


class ProceedingsParserTests(SimpleTestCase):
    def test_miccai_json_flips_names_and_resolves_links(self):
        body = json.dumps([{
            'title': 'Cell Typing in H&amp;E Slides', 'url': '/miccai-2026/0001-Paper2705.html',
            'authors': 'Noh, Jeonghyun AND Oh, Hyun-Jic', 'pdflink': 'https://papers.miccai.org/miccai-2026/paper/2705_paper.pdf',
        }])
        [record] = parse('miccai_json', body, url='https://papers.miccai.org/miccai-2026/js/search.json')
        self.assertEqual(record['title'], 'Cell Typing in H&E Slides')
        self.assertEqual(record['authors'], 'Jeonghyun Noh, Hyun-Jic Oh')
        self.assertEqual(record['url'], 'https://papers.miccai.org/miccai-2026/paper/2705_paper.pdf')
        self.assertEqual(record['pdf_url'], record['url'])

    def test_miccai_json_falls_back_to_the_paper_page_without_a_pdf(self):
        body = json.dumps([{'title': 'A Paper Without Its PDF Yet', 'url': '/miccai-2026/0002-Paper1.html',
                            'authors': 'Noh, Jeonghyun', 'pdflink': ''}])
        [record] = parse('miccai_json', body, url='https://papers.miccai.org/miccai-2026/js/search.json')
        self.assertEqual((record['url'], record['pdf_url']), ('https://papers.miccai.org/miccai-2026/0002-Paper1.html', ''))

    def test_miccai_json_splits_lowercase_and_between_authors(self):
        body = json.dumps([{'title': 'A MICCAI 2024 Paper Title', 'url': '/p.html', 'pdflink': '/p.pdf',
                            'authors': 'Alsharid, Mohammad and Papageorghiou, Aris T. and Noble, J. Alison'}])
        [record] = parse('miccai_json', body)
        self.assertEqual(record['authors'], 'Mohammad Alsharid, Aris T. Papageorghiou, J. Alison Noble')

    def test_virtual_site_json_picks_paper_page_and_pdf(self):
        body = json.dumps({'results': [
            {'name': 'NeurIPS Paper', 'authors': [{'fullname': 'Ada Lovelace'}, {'fullname': 'Alan Turing'}],
             'paper_url': 'https://openreview.net/forum?id=abc123', 'paper_pdf_url': None,
             'virtualsite_url': '/virtual/2025/poster/1'},
            {'name': 'CVPR Paper', 'authors': [], 'paper_url': '',
             'paper_pdf_url': 'https://openaccess.thecvf.com/content/CVPR2025/html/P.html',
             'virtualsite_url': '/virtual/2025/poster/2'},
            {'name': 'Session Only Paper', 'authors': None, 'paper_url': None, 'paper_pdf_url': 'None',
             'virtualsite_url': '/virtual/2025/poster/3'},
        ]})
        neurips, cvpr, bare = parse('virtual_site_json', body, url='https://neurips.cc/static/virtual/data/x.json')
        self.assertEqual(neurips['authors'], 'Ada Lovelace, Alan Turing')
        self.assertEqual(neurips['url'], 'https://openreview.net/forum?id=abc123')
        self.assertEqual(neurips['pdf_url'], 'https://openreview.net/pdf?id=abc123')
        self.assertEqual(cvpr['url'], 'https://openaccess.thecvf.com/content/CVPR2025/html/P.html')
        self.assertEqual(cvpr['pdf_url'], '')
        self.assertEqual(bare['url'], 'https://neurips.cc/virtual/2025/poster/3')

    def test_cvf_html_reads_title_authors_and_pdf(self):
        first, second = parse('cvf_html', CVF_PAGE, url='https://openaccess.thecvf.com/CVPR2026?day=all')
        self.assertEqual(first['title'], 'Keypoint Correspondence for Object Tracking')
        self.assertEqual(first['authors'], 'Jie Xiao, Yinchao Ma')
        self.assertEqual(first['url'], 'https://openaccess.thecvf.com/content/CVPR2026/html/A_paper.html')
        self.assertEqual(first['pdf_url'], 'https://openaccess.thecvf.com/content/CVPR2026/papers/A_paper.pdf')
        self.assertEqual((second['authors'], second['pdf_url']), ('', ''))

    def test_ecva_page_is_filtered_to_one_year(self):
        [record] = parse('cvf_html', ECVA_PAGE, url='https://www.ecva.net/papers.php', href_contains='eccv_2024')
        self.assertEqual(record['authors'], 'Jacopo Bonato, Marco Cotogni, Luigi Sabetta')
        self.assertEqual(record['pdf_url'], 'https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/00004.pdf')

    def test_html_selectors_requires_an_item_selector(self):
        page = '''<div class="p"><b>A Generic Paper Title Here</b><i>Ada Lovelace, Alan Turing</i>
                  <a href="/p1.html">info</a><a href="/p1.pdf">pdf</a></div>'''
        with self.assertRaises(ValueError):
            parse('html_selectors', page)
        [record] = parse('html_selectors', page, item='div.p', title='b', authors='i', pdf='a[href$=".pdf"]')
        self.assertEqual(record['title'], 'A Generic Paper Title Here')
        self.assertEqual(record['authors'], 'Ada Lovelace, Alan Turing')
        self.assertEqual(record['url'], 'https://example.org/p1.html')
        self.assertEqual(record['pdf_url'], 'https://example.org/p1.pdf')

    def test_html_links_keeps_only_title_like_links(self):
        page = '''<a href="/home">Home</a><a href="/paper/1">A Long Enough Paper Title</a>
                  <a href="/news/2">Another Long Enough Link Text</a>'''
        records = parse('html_links', page, href_contains='/paper/')
        self.assertEqual([r['url'] for r in records], ['https://example.org/paper/1'])

    def test_short_titles_duplicates_and_non_http_links_are_dropped(self):
        records = proceedings._clean_records([
            {'title': 'Short', 'url': 'https://example.org/1', 'authors': '', 'pdf_url': ''},
            {'title': 'A Valid Paper Title', 'url': 'javascript:void(0)', 'authors': '', 'pdf_url': ''},
            {'title': 'A Valid Paper Title', 'url': 'https://example.org/2', 'authors': '', 'pdf_url': ''},
            {'title': 'A valid paper  title', 'url': 'https://example.org/3', 'authors': '', 'pdf_url': ''},
        ])
        self.assertEqual([r['url'] for r in records], ['https://example.org/2'])
        self.assertEqual(records[0]['normalized_title'], 'valid paper title')

    def test_every_parser_choice_has_a_parser_and_a_guide_entry(self):
        choices = {key for key, _ in ProceedingsSource.PARSER_CHOICES}
        self.assertEqual(choices, set(proceedings.PARSERS))
        self.assertEqual(choices, {row['parser'] for row in proceedings.PARSER_GUIDE})


class TextCleaningTests(SimpleTestCase):
    def test_latex_in_titles_becomes_plain_text(self):
        cases = {
            r'{$\tau$}-bench: \underline{T}ool-\underline{A}gent Interaction': 'τ-bench: Tool-Agent Interaction',
            r'$\boldsymbol{\mu}\mathbf{P^2}$: Sharpness Aware Minimization': 'μP²: Sharpness Aware Minimization',
            r'\(\varepsilon\)-Optimally Solving Zero-Sum POSGs': 'ε-Optimally Solving Zero-Sum POSGs',
            r'$\alpha$Matte4K \& $\mu$Matting: Dataset and Model': 'αMatte4K & μMatting: Dataset and Model',
            r'$\mathbb{R}^{2k}$ is Large Enough for Top-$k$ Retrieval': 'R^(2k) is Large Enough for Top-k Retrieval',
            r'(FL)$^2$: Overcoming Few Labels': '(FL)²: Overcoming Few Labels',
        }
        for raw, clean in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(proceedings._title_text(raw), clean)

    def test_quotes_are_unwrapped_or_made_typographic(self):
        self.assertEqual(proceedings._title_text('"BK-SDM: A Lightweight Version of Stable Diffusion"'),
                         'BK-SDM: A Lightweight Version of Stable Diffusion')
        self.assertEqual(proceedings._title_text('From ``Sure" to ``Sorry": Detecting Jailbreaks'),
                         'From “Sure” to “Sorry”: Detecting Jailbreaks')
        self.assertEqual(proceedings._title_text("Is `Right' Right? Object Orientation"),
                         'Is ‘Right’ Right? Object Orientation')

    def test_trailing_periods_are_dropped_except_after_abbreviations(self):
        self.assertEqual(proceedings._title_text('Efficient Image Editing via Token Reuse.'), 'Efficient Image Editing via Token Reuse')
        self.assertEqual(proceedings._title_text('Benchmarks by Smith et al.'), 'Benchmarks by Smith et al.')

    def test_plain_text_is_left_alone(self):
        for title in ('Saving $100 with Budget-Aware Training', 'How <SEG> Token Works', 'D^M: Deformation-Driven Diffusion'):
            self.assertEqual(proceedings._title_text(title), title)

    def test_author_names_lose_entities_accent_markup_and_invisible_characters(self):
        cases = {
            "R{{\\&#x27;e}}mi Munos, Fearghal O&amp;#x27;Donncha": "Rémi Munos, Fearghal O'Donncha",
            '\u202aYotam Alexander\u202c\u200f, Yonatan Slutzky': 'Yotam Alexander, Yonatan Slutzky',
            'Riccardo D`Elia': "Riccardo D'Elia",
            'Fran{\\c{c}}ois Fleuret, J{\\"o}rg Mayer, \\v{S}imon Ko\\v{s}': 'François Fleuret, Jörg Mayer, Šimon Koš',
        }
        for raw, clean in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(proceedings._text(raw), clean)


class ProceedingsSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.source = ProceedingsSource.objects.create(
            conference='MICCAI', year=2026, url='https://example.org/search.json', parser='miccai_json')
        ProceedingsPaper.objects.create(source=self.source, title='Old Paper Title', normalized_title='old paper title',
                                        url='https://example.org/old')
        self.download = self.enterContext(patch.object(proceedings, '_download_capped'))

    def sync(self):
        result = proceedings.sync_sources([self.source.pk])
        self.source.refresh_from_db()
        return result

    def test_sync_replaces_the_list_and_records_status(self):
        self.download.return_value = (json.dumps([
            {'title': FEDAGREE, 'url': '/p/1.html', 'authors': 'Serra, Giuseppe', 'pdflink': '/p/1.pdf'},
        ]).encode(), 'application/json')
        self.assertEqual(self.sync(), {'MICCAI 2026': 'ok'})
        paper = self.source.papers.get()
        self.assertEqual((paper.title, paper.authors), (FEDAGREE, 'Giuseppe Serra'))
        self.assertEqual((self.source.last_status, self.source.paper_count), ('ok', 1))
        self.assertIsNotNone(self.source.last_synced_at)

    def test_failed_empty_or_invalid_downloads_keep_the_previous_list(self):
        for payload, status in (((None, ''), 'error'), ((b'[]', 'application/json'), 'empty'),
                                ((b'<html>', 'text/html'), 'error')):
            with self.subTest(status=status):
                self.download.return_value = payload
                self.sync()
                self.assertEqual(self.source.last_status, status)
                self.assertEqual(self.source.papers.get().title, 'Old Paper Title')

    def test_disabled_and_busy_sources_are_skipped(self):
        cache.add(f'proceedings-sync:{self.source.pk}', True)
        self.assertEqual(self.sync(), {'MICCAI 2026': 'busy'})
        self.source.enabled = False
        self.source.save()
        self.assertEqual(self.sync(), {})
        self.download.assert_not_called()

    def test_management_command_syncs_selected_sources(self):
        self.download.return_value = (None, '')
        out = io.StringIO()
        call_command('sync_proceedings', str(self.source.pk), stdout=out)
        self.assertIn('MICCAI 2026: error', out.getvalue())

    def test_seeded_sources_use_known_parsers(self):
        seeded = ProceedingsSource.objects.exclude(pk=self.source.pk)
        self.assertTrue(seeded.filter(conference='MICCAI', year=2026, parser='miccai_json').exists())
        self.assertTrue(seeded.filter(conference='ECCV', options={'href_contains': 'eccv_2024'}).exists())
        self.assertFalse(seeded.exclude(parser__in=proceedings.PARSERS).exists())


class ProceedingsMatchTests(TestCase):
    def setUp(self):
        self.enterContext(patch.object(search.requests, 'get', side_effect=AssertionError('Unexpected network request')))
        self.miccai = self.add_source('MICCAI')

    def add_source(self, conference, year=2026):
        return ProceedingsSource.objects.create(
            conference=conference, year=year, url=f'https://example.org/{conference}{year}', parser='miccai_json')

    def add(self, title, authors='', src=None, url='https://example.org/paper'):
        return ProceedingsPaper.objects.create(
            source=src or self.miccai, title=title, normalized_title=search.normalize_title(title),
            authors=authors, url=url, pdf_url=url + '.pdf')

    def test_misread_acronym_matches_when_authors_confirm(self):
        self.add(RALMPH, RALMPH_AUTHORS)
        self.assertIsNone(search._search_proceedings(RALPH_POSTER))
        paper = search._search_proceedings(RALPH_POSTER, 'Sungrae Hong, Jiwon Jeong')
        self.assertEqual(paper['title'], RALMPH)
        self.assertEqual((paper['source'], paper['conference'], paper['year']), ('proceedings', 'MICCAI 2026', 2026))

    def test_last_name_first_poster_authors_still_confirm(self):
        self.add(RALMPH, RALMPH_AUTHORS)
        self.assertIsNotNone(search._search_proceedings(RALPH_POSTER, 'Hong, Sungrae, Jeong, Jiwon'))

    def test_truncated_poster_title_matches_when_authors_confirm(self):
        full = ('Self-supervised Normality Learning and Divergence Vector-guided Model Merging '
                'for Zero-shot Congenital Heart Disease Detection in Fetal Ultrasound Videos')
        poster = 'Self-supervised Normality Learning and Divergence Vector-guided Model Merging'
        self.add(full, 'Pramit Saha, Divyanshu Mishra, Netzahualcoyotl Hernandez-Cruz')
        self.assertIsNone(search._search_proceedings(poster))
        self.assertIsNone(search._search_proceedings(poster, 'Someone Else, Another Person'))
        self.assertEqual(search._search_proceedings(poster, 'Pramit Saha, Divyanshu Mishra')['title'], full)

    def test_truncation_rule_needs_a_long_enough_title(self):
        self.add('Federated Medical Imaging Analysis Under Distribution Shift', 'Giuseppe Serra, Ben Werner')
        self.assertIsNone(search._search_proceedings('Federated Imaging Analysis', 'Giuseppe Serra, Ben Werner'))

    def test_versioned_acronyms_never_match_even_with_the_same_authors(self):
        self.add(SKIN.replace('Skin-R1', 'Skin-R2'), 'Zehao Liu, Weijieying Ren')
        self.assertIsNone(search._search_proceedings(SKIN, 'Zehao Liu, Weijieying Ren'))

    def test_unrelated_papers_with_shared_words_are_rejected(self):
        self.add('Federated Medical Imaging Benchmarks for Distribution Shift', 'Giuseppe Serra')
        self.assertIsNone(search._search_proceedings(FEDAGREE, 'Giuseppe Serra'))

    def test_conference_hint_breaks_ties_and_disabled_sources_are_ignored(self):
        cvpr = self.add_source('CVPR')
        self.add(FEDAGREE, url='https://example.org/miccai')
        self.add(FEDAGREE, src=cvpr, url='https://example.org/cvpr')
        self.assertEqual(search._search_proceedings(FEDAGREE, conference='CVPR 2026')['paper_url'], 'https://example.org/cvpr')
        cvpr.enabled = False
        cvpr.save()
        self.assertEqual(search._search_proceedings(FEDAGREE, conference='CVPR 2026')['paper_url'], 'https://example.org/miccai')

    def test_search_paper_checks_proceedings_before_online_sources(self):
        self.add(FEDAGREE, 'Giuseppe Serra, Ben Werner')
        with patch.object(search, '_get_arxiv_paper') as arxiv:
            paper = search.search_paper(FEDAGREE, arxiv_id='2501.00001')
        arxiv.assert_not_called()
        self.assertEqual(paper['paper_url'], 'https://example.org/paper')

    def test_online_search_still_runs_when_nothing_matches(self):
        online = {**search._paper(title=FEDAGREE, paper_url='https://arxiv.org/abs/2501.00001'), 'source': 'arxiv'}
        with patch.object(search, '_search_arxiv', return_value=[online]):
            self.assertEqual(search.search_paper(FEDAGREE)['source'], 'arxiv')

    def test_database_errors_fall_back_to_online_sources(self):
        with patch.object(search.ProceedingsPaper.objects, 'filter', side_effect=DatabaseError):
            self.assertIsNone(search._search_proceedings(FEDAGREE))

    def test_enrichment_takes_year_and_conference_from_the_proceedings(self):
        self.add(RALMPH, RALMPH_AUTHORS, url='https://papers.miccai.org/miccai-2026/0853-Paper1120.html')
        info = {'is_research_poster': True, 'title': RALPH_POSTER, 'authors': 'Sungrae Hong, Jiwon Jeong',
                'conference': 'MICCAI 2023', 'year': '2023'}
        with patch.object(ai, 'extract_poster_info', return_value=info), \
                patch.object(ai, '_find_real_pdf', side_effect=lambda pdf_url_hint, **_: pdf_url_hint), \
                patch.object(ai, 'find_github_repo', return_value=''), \
                patch.object(ai, '_generate_description_from_pdf', return_value='PDF summary'):
            result = ai.analyze_and_enrich('unused')
        self.assertEqual(result['paper_link'], 'https://papers.miccai.org/miccai-2026/0853-Paper1120.html')
        self.assertEqual((result['conference'], result['publication_year']), ('MICCAI 2026', 2026))
        self.assertEqual(result['authors'], RALMPH_AUTHORS)

    def test_repair_fills_link_and_blank_conference(self):
        self.add(FEDAGREE, 'Giuseppe Serra', url='https://papers.miccai.org/miccai-2026/0379-Paper5130.html')
        poster = ResearchPoster.objects.create(title=FEDAGREE, authors='Giuseppe Serra', summary='s',
                                               image='posters/t.jpg', image_sha256='b' * 64)
        call_command('repair_paper_links', str(poster.pk), apply=True, stdout=io.StringIO())
        poster.refresh_from_db()
        self.assertEqual(poster.paper_link, 'https://papers.miccai.org/miccai-2026/0379-Paper5130.html')
        self.assertEqual((poster.conference, poster.publication_year), ('MICCAI 2026', 2026))


class ProceedingsAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', 'admin@example.org', 'pw'))
        self.delay = self.enterContext(patch('bot_engine.admin.sync_proceedings_task.delay'))

    def test_list_shows_the_scraper_guide(self):
        response = self.client.get('/admin/bot_engine/proceedingssource/')
        self.assertContains(response, 'Scraper guide')
        for row in proceedings.PARSER_GUIDE:
            self.assertContains(response, row['parser'])

    def test_adding_a_source_queues_its_first_sync(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/admin/bot_engine/proceedingssource/add/', {
                'conference': 'ECCV', 'year': 2026, 'url': 'https://www.ecva.net/papers.php',
                'parser': 'cvf_html', 'options': '{"href_contains": "eccv_2026"}', 'enabled': 'on',
            })
        self.assertEqual(response.status_code, 302)
        source = ProceedingsSource.objects.get(conference='ECCV', year=2026)
        self.delay.assert_called_once_with([source.pk])

    def test_sync_action_queues_enabled_sources(self):
        enabled = ProceedingsSource.objects.filter(enabled=True).values_list('pk', flat=True)
        self.client.post('/admin/bot_engine/proceedingssource/', {
            'action': 'sync_now', '_selected_action': list(enabled),
        })
        self.delay.assert_called_once_with(list(enabled))
