from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='presence',
            name='missed_scans',
            field=models.PositiveIntegerField(default=0, verbose_name='Пропущенные сканы'),
        ),
    ]
