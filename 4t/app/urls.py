from django.urls import path
from .views import knowledge_form_view, submit_answers, result_page, home_view

urlpatterns = [
    path('', home_view, name='home'),
    path('knowledge-form/', knowledge_form_view, name='knowledge_form'),
    path('submit-answers/', submit_answers, name='submit_answers'),
    path('result/', result_page, name='result_page'),
]
