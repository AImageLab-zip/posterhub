from django.db import migrations

CVF = 'https://openaccess.thecvf.com/{}{}?day=all'
VIRTUAL = 'https://{site}/static/virtual/data/{conf}-{year}-orals-posters.json'

SOURCES = [
    *[('MICCAI', year, f'https://papers.miccai.org/miccai-{year}/js/search.json', 'miccai_json', {})
      for year in (2024, 2025, 2026)],
    ('CVPR', 2025, CVF.format('CVPR', 2025), 'cvf_html', {}),
    ('CVPR', 2026, CVF.format('CVPR', 2026), 'cvf_html', {}),
    ('ICCV', 2025, CVF.format('ICCV', 2025), 'cvf_html', {}),
    ('WACV', 2026, CVF.format('WACV', 2026), 'cvf_html', {}),
    ('ECCV', 2024, 'https://www.ecva.net/papers.php', 'cvf_html', {'href_contains': 'eccv_2024'}),
    *[(label, year, VIRTUAL.format(site=site, conf=conf, year=year), 'virtual_site_json', {})
      for label, site, conf, years in (
          ('NeurIPS', 'neurips.cc', 'neurips', (2024, 2025)),
          ('ICML', 'icml.cc', 'icml', (2025, 2026)),
          ('ICLR', 'iclr.cc', 'iclr', (2025, 2026)),
      ) for year in years],
]


def seed_sources(apps, schema_editor):
    ProceedingsSource = apps.get_model('bot_engine', 'ProceedingsSource')
    for conference, year, url, parser, options in SOURCES:
        ProceedingsSource.objects.get_or_create(
            conference=conference, year=year, url=url,
            defaults={'parser': parser, 'options': options},
        )


def remove_sources(apps, schema_editor):
    ProceedingsSource = apps.get_model('bot_engine', 'ProceedingsSource')
    for conference, year, url, _, _ in SOURCES:
        ProceedingsSource.objects.filter(conference=conference, year=year, url=url).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bot_engine', '0030_proceedings'),
    ]

    operations = [
        migrations.RunPython(seed_sources, remove_sources),
    ]
