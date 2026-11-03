from django.db import migrations, models


def rename_the_join_button(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    # The old wording pointed at two separate pages; one form does it all now.
    SiteSettings.objects.filter(home_call_to_action="Become a member").update(
        home_call_to_action="Register as a Member"
    )


def restore_the_old_wording(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(home_call_to_action="Register as a Member").update(
        home_call_to_action="Become a member"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_storedfile"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="home_call_to_action",
            field=models.CharField(default="Register as a Member", max_length=60),
        ),
        migrations.RunPython(rename_the_join_button, restore_the_old_wording),
    ]
