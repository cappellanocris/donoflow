from .models import CmsPage, FooterSection


def cms_pages(request):
    published = CmsPage.objects.filter(is_published=True)
    return {
        'navigation_pages': published.filter(show_in_navigation=True),
        'footer_pages': published.filter(show_in_footer=True),
        'footer_sections': FooterSection.objects.filter(is_active=True).order_by('sort_order', 'id'),
    }


def user_roles(request):
    """Espone i ruoli ai template: prima il menu usava solo `is_staff`, quindi gli
    utenti del gruppo "operatori" non vedevano la propria area."""
    from .views import is_admin_user, is_operator
    user = request.user
    if not user.is_authenticated:
        return {'user_is_operator': False, 'user_is_admin': False, 'user_is_donor': False}
    return {
        'user_is_operator': is_operator(user),
        'user_is_admin': is_admin_user(user),
        'user_is_donor': hasattr(user, 'donor_profile'),
    }
