# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-04-05 15:52
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('mailqueue', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='queuedmail',
            name='sendtime',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='queuedmail',
            name='subject',
            field=models.CharField(default='', max_length=500),
            preserve_default=False,
        ),
    ]
