from django.db import migrations, models


def seed_footer_sections(apps, schema_editor):
    FooterSection = apps.get_model('core', 'FooterSection')
    defaults = [
        {
            'key': 'ABOUT',
            'title': 'DonoFlow',
            'content': '<p>DonoFlow semplifica la prenotazione delle donazioni di sangue e aiuta gli organizzatori a gestire raccolte, slot e liste d’attesa.</p>',
            'is_active': True,
            'sort_order': 10,
        },
        {
            'key': 'LINKS',
            'title': 'Link utili',
            'content': '<ul><li><a href="/sessions/">Raccolte disponibili</a></li><li><a href="/come-funziona/">Come funziona</a></li><li><a href="/area-personale/">Area personale</a></li></ul>',
            'is_active': True,
            'sort_order': 20,
        },
        {
            'key': 'CONTACTS',
            'title': 'Informazioni e contatti',
            'content': '<p>Sviluppato da <strong>Cris Cappellano</strong>, consulente informatico e sistemista.</p><p><a href="mailto:criscappellano@gmail.com">criscappellano@gmail.com</a></p>',
            'is_active': True,
            'sort_order': 30,
        },
    ]
    for data in defaults:
        FooterSection.objects.update_or_create(key=data['key'], defaults=data)


def unseed_footer_sections(apps, schema_editor):
    FooterSection = apps.get_model('core', 'FooterSection')
    FooterSection.objects.filter(key__in=['ABOUT', 'LINKS', 'CONTACTS']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_seed_default_pages'),
    ]

    operations = [
        migrations.CreateModel(
            name='FooterSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(choices=[('ABOUT', 'Presentazione'), ('LINKS', 'Link utili'), ('CONTACTS', 'Contatti')], max_length=20, unique=True, verbose_name='Sezione')),
                ('title', models.CharField(max_length=100, verbose_name='Titolo')),
                ('content', models.TextField(help_text='Puoi usare HTML semplice, inclusi paragrafi, elenchi e link.', verbose_name='Contenuto HTML')),
                ('is_active', models.BooleanField(default=True, verbose_name='Visibile nel footer')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Ordine')),
            ],
            options={
                'verbose_name': 'Sezione footer',
                'verbose_name_plural': 'Sezioni footer',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.RunPython(seed_footer_sections, unseed_footer_sections),
    ]
