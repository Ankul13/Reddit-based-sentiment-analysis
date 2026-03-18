from django.urls import path
from core import views

urlpatterns = [
    path('',                             views.home,         name='home'),
    path('analyze/',                     views.analyze,      name='analyze'),
    path('analyze/run/',                 views.run_analysis, name='run_analysis'),
    path('analyze/status/<int:job_id>/', views.job_status,   name='job_status'),
    path('dashboard/<int:job_id>/',      views.dashboard,    name='dashboard'),
    path('history/',                     views.history,      name='history'),
    path('history/delete/<int:job_id>/', views.delete_job,   name='delete_job'),
    path('hive/',                        views.hive,         name='hive'),
    path('about/',                       views.about,        name='about'),
]
