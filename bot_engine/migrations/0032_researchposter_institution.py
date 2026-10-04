from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bot_engine', '0031_seed_proceedings_sources'),
    ]

    operations = [
        migrations.AddField(
            model_name='researchposter',
            name='institution',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
