from django.contrib import admin
from django.urls import path, include
from tracker.views import custom_login
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', custom_login, name='login'),
    path('accounts/', include('django.contrib.auth.urls')),  # includes logout
    path('', include('tracker.urls')),
] + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
