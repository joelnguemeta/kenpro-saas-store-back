from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_passwordresettoken"),
    ]

    operations = [
        migrations.RenameField(
            model_name="passwordresettoken",
            old_name="token",
            new_name="token_hash",
        ),
        migrations.RenameField(
            model_name="pinresettoken",
            old_name="token",
            new_name="token_hash",
        ),
    ]
