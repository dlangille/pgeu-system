# Generated by Django 3.2.14 on 2023-12-18 14:27

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('confreg', '0107_conference_scannerfields'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='conferencesessionfeedback',
            unique_together={('attendee', 'session', 'conference')},
        ),
    ]