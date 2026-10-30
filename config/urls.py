from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = f"{settings.ORGANIZATION_NAME} - Site Administration"
admin.site.site_title = settings.ORGANIZATION_NAME
admin.site.index_title = "Content & records"

urlpatterns = [
    path("", include("apps.core.urls")),
    path("django-admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("member/", include("apps.membership.urls")),
    path("events/", include("apps.events.urls")),
    path("contributions/", include("apps.contributions.urls")),
    path("incidents/", include("apps.incidents.urls")),
    path("admin-panel/", include("apps.admin_panel.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
