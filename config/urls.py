from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from apps.core import views as core_views

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

if settings.MEDIA_STORAGE == "database":
    # Uploads are rows in the database, so the app serves them itself - there is no
    # shared disk on Render for nginx to point at.
    urlpatterns.append(re_path(r"^media/(?P<path>.+)$", core_views.media, name="media"))
elif settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
