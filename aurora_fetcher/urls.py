"""aurora_fetcher URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url
from django.urls import include, re_path
from client.views import HomeView
from transformer.models import SourceObject
from transformer.views import SourceObjectViewSet, ConsumerObjectViewSet
from rest_framework import routers
from rest_framework_jwt.views import obtain_jwt_token

router = routers.DefaultRouter()
router.register(r'^source_objects', SourceObjectViewSet, 'source_object')
router.register(r'^consumer_objects', ConsumerObjectViewSet, 'consumer_object')

urlpatterns = [
    re_path(r'^$', HomeView.as_view(), name='home'),
    url(r'', include(router.urls)),
    url(r'^get-token/', obtain_jwt_token),
    url(r'^', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^status/', include('health_check.api.urls')),
    url(r'^admin/', admin.site.urls),
]