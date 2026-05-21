from django.urls import path

from . import views

app_name = 'attendance'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/status/', views.api_status, name='api_status'),
    path('scan/', views.scan_now, name='scan_now'),
]
