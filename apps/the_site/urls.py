from django.urls import path, include

urlpatterns = [
    path('', include('service_provider.urls')),
]
