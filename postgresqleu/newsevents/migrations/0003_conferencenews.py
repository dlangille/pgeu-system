# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-09-21 16:35
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import postgresqleu.util.validators


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0008_alter_user_username_max_length'),
        ('newsevents', '0002_drop_standalone_events'),
    ]

    operations = [
        migrations.CreateModel(
            name='NewsPosterProfile',
            fields=[
                ('author', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
                ('urlname', models.CharField(max_length=50, unique=True, verbose_name="URL name", validators=[postgresqleu.util.validators.validate_urlname])),
                ('fullname', models.CharField(max_length=100, verbose_name="Full name")),
                ('canpostglobal', models.BooleanField(default=False, verbose_name="Can post global news")),
            ],
        ),
        migrations.AddField(
            model_name='news',
            name='highpriorityuntil',
            field=models.DateTimeField(null=True, blank=True, verbose_name='High priority until'),
        ),
        migrations.AddField(
            model_name='news',
            name='inarchive',
            field=models.BooleanField(default=True, verbose_name='Include in archives'),
        ),
        migrations.AddField(
            model_name='news',
            name='inrss',
            field=models.BooleanField(default=True, verbose_name='Include in RSS feed'),
        ),
        migrations.AddField(
            model_name='news',
            name='author',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='newsevents.NewsPosterProfile'),
        ),
    ]
