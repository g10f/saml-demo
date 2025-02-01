from django.urls import path

from service_provider.views import index, metadata

app_name = 'service_provider'

urlpatterns = [
    path('', index, name='index'),
    path('metadata/', metadata, name='metadata'),
]