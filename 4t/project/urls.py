from django.contrib import admin
from django.urls import path, include
from app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home_view, name='home'),
    path('app/', include('app.urls')),
    path('knowledge-form/', views.knowledge_form_view, name='knowledge_form'),
    path('submit-answers/', views.submit_answers, name='submit_answers'),
    path('result/', views.result_page, name='result_page'),
]
