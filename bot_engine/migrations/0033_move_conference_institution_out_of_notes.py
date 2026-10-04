import re

from django.db import migrations

# Notes used to be filled with "Auto-extracted by AI. Conference: X, Institution: Y" when the
# uploader wrote none. Both values now have their own fields, so move them there and clear
# the generated text. Notes written by users are left untouched.
AUTO_NOTES = re.compile(
    r"^Auto-extracted by AI\.\s*Conference:\s*(?P<conference>.*?),\s*Institution:\s*(?P<institution>.*)$",
    re.S,
)
PLACEHOLDERS = {"n/a", "na", "none", "null", "unknown", "not visible"}


def parse_auto_notes(notes):
    match = AUTO_NOTES.match((notes or "").strip())
    if not match:
        return None
    return {key: "" if value.strip().lower() in PLACEHOLDERS else " ".join(value.split())
            for key, value in match.groupdict().items()}


def forwards(apps, schema_editor):
    ResearchPoster = apps.get_model("bot_engine", "ResearchPoster")
    posters = ResearchPoster.objects.filter(notes__startswith="Auto-extracted by AI.")
    for poster in posters.only("pk", "notes", "conference", "institution"):
        values = parse_auto_notes(poster.notes)
        if values is None:
            continue
        # .update() rather than .save() so updated_at is not bumped on every poster.
        ResearchPoster.objects.filter(pk=poster.pk).update(
            notes="",
            conference=poster.conference or values["conference"][:200],
            institution=poster.institution or values["institution"][:500],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('bot_engine', '0032_researchposter_institution'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
