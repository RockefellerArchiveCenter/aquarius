"""aquarius URL Configuration

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
from asterism.views import PingView
from django.contrib import admin
from django.urls import include, re_path
from rest_framework import routers
from rest_framework.schemas import get_schema_view

from transformer.views import (AccessionUpdateRequestView, PackageViewSet,
                               ProcessAccessionsView,
                               ProcessDigitalObjectsView,
                               ProcessGroupingComponentsView,
                               ProcessTransferComponentsView,
                               TransferUpdateRequestView)

router = routers.DefaultRouter()
router.register(r'packages', PackageViewSet, 'package')

schema_view = get_schema_view(
    title="Aquarius API",
    description="Endpoints for Aquarius microservice application."
)

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^accessions/', ProcessAccessionsView.as_view(), name="accessions"),
    re_path(r'^grouping-components/', ProcessGroupingComponentsView.as_view(), name="grouping-components"),
    re_path(r'^transfer-components/', ProcessTransferComponentsView.as_view(), name="transfer-components"),
    re_path(r'^digital-objects/', ProcessDigitalObjectsView.as_view(), name="digital-objects"),
    re_path(r'^send-update/', TransferUpdateRequestView.as_view(), name="send-update"),
    re_path(r'^send-accession-update/', AccessionUpdateRequestView.as_view(), name="send-accession-update"),
    re_path(r'^status/', PingView.as_view(), name='ping'),
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^schema/', schema_view, name='schema'),
]
