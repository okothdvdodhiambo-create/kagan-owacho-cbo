from django.db import migrations, models


def clear_blank_numbers(apps, schema_editor):
    Member = apps.get_model("membership", "Member")
    Member.objects.filter(membership_no="").update(membership_no=None)


class Migration(migrations.Migration):
    """A membership number only exists once a member is verified.

    Empty strings broke the unique index as soon as a second person registered,
    so pending members now hold NULL.
    """

    dependencies = [
        ("membership", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="membership_no",
            field=models.CharField(blank=True, editable=False, max_length=20, null=True, unique=True),
        ),
        migrations.RunPython(clear_blank_numbers, migrations.RunPython.noop),
    ]
