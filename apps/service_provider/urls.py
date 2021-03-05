from django.urls import path

from service_provider.views import index, attrs, metadata

app_name = 'service_provider'

urlpatterns = [
    path('', index, name='index'),
    path('attrs/', attrs, name='attrs'),
    path('metadata/', metadata, name='metadata'),
]