from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import CmsPage


class CmsPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username='admin-test',
            email='admin@example.com',
            password='test-password-123',
        )
        cls.page = CmsPage.objects.create(
            title='Pagina pubblica',
            slug='pagina-pubblica',
            menu_label='Pubblica',
            summary='Una pagina di prova',
            content='<h2>Contenuto</h2><p>Test</p>',
            is_published=True,
            show_in_navigation=True,
            show_in_footer=True,
        )

    def test_published_page_is_visible(self):
        response = self.client.get(reverse('public_page', kwargs={'slug': self.page.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pagina pubblica')
        self.assertContains(response, '<h2>Contenuto</h2>', html=True)

    def test_hidden_page_returns_404(self):
        self.page.is_published = False
        self.page.save(update_fields=['is_published'])
        response = self.client.get(reverse('public_page', kwargs={'slug': self.page.slug}))
        self.assertEqual(response.status_code, 404)

    def test_admin_can_create_page(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('management_page_create'), {
            'title': 'Nuova pagina',
            'slug': 'nuova-pagina',
            'menu_label': 'Nuova',
            'summary': 'Descrizione',
            'content': '<p>Nuovo contenuto</p>',
            'is_published': 'on',
            'show_in_footer': 'on',
            'sort_order': 20,
        })
        self.assertRedirects(response, reverse('management_pages'))
        self.assertTrue(CmsPage.objects.filter(slug='nuova-pagina').exists())

    def test_non_admin_cannot_access_page_management(self):
        user = User.objects.create_user(username='normal-user', password='password-123')
        self.client.force_login(user)
        response = self.client.get(reverse('management_pages'))
        # Utente autenticato senza permessi: 403 esplicito (prima: redirect al login).
        self.assertEqual(response.status_code, 403)


class PublicSessionsFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import date
        from django.utils import timezone
        from .models import DonationCenter, DonationSession

        future_year = timezone.localdate().year + 1
        cls.future_year = future_year
        cls.center_a = DonationCenter.objects.create(name='Sede A', city='Carini', active=True)
        cls.center_b = DonationCenter.objects.create(name='Sede B', city='Palermo', active=True)
        cls.session_january = DonationSession.objects.create(
            center=cls.center_a,
            title='Raccolta gennaio',
            date=date(future_year, 1, 10),
            status='OPEN',
        )
        cls.session_february = DonationSession.objects.create(
            center=cls.center_b,
            title='Raccolta febbraio',
            date=date(future_year, 2, 10),
            status='OPEN',
        )

    def test_filter_sessions_by_center(self):
        response = self.client.get(reverse('sessions_list'), {'center': self.center_a.pk})
        self.assertContains(response, 'Raccolta gennaio')
        self.assertNotContains(response, 'Raccolta febbraio')

    def test_filter_sessions_by_month_and_year(self):
        response = self.client.get(reverse('sessions_list'), {
            'month': 2,
            'year': self.future_year,
        })
        self.assertContains(response, 'Raccolta febbraio')
        self.assertNotContains(response, 'Raccolta gennaio')


class FooterSectionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import FooterSection

        cls.admin = User.objects.create_superuser(
            username='footer-admin',
            email='footer@example.com',
            password='test-password-123',
        )
        cls.section, _ = FooterSection.objects.update_or_create(
            key='ABOUT',
            defaults={
                'title': 'Sezione test',
                'content': '<p>Contenuto footer</p>',
                'is_active': True,
                'sort_order': 1,
            },
        )

    def test_active_footer_section_is_rendered(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Sezione test')
        self.assertContains(response, 'Contenuto footer')

    def test_admin_can_update_footer_section(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('management_footer_update', args=[self.section.pk]), {
            'title': 'Titolo aggiornato',
            'content': '<p>Testo aggiornato</p>',
            'is_active': 'on',
            'sort_order': 5,
        })
        self.assertRedirects(response, reverse('management_footer'))
        self.section.refresh_from_db()
        self.assertEqual(self.section.title, 'Titolo aggiornato')
        self.assertEqual(self.section.sort_order, 5)
