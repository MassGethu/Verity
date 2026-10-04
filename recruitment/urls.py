from django.urls import path
from . import views
urlpatterns=[
 path('',views.landing,name='home'),path('dashboard/',views.home,name='dashboard'),path('jobs/new/',views.job_create,name='job_create'),
 path('jobs/<int:pk>/setup/',views.job_setup,name='job_setup'),path('jobs/<int:pk>/',views.workspace,name='workspace'),path('jobs/<int:pk>/upload/',views.upload,name='upload'),
 path('applications/<int:pk>/',views.candidate_detail,name='candidate'),path('applications/<int:pk>/process/',views.process,name='process'),path('applications/<int:pk>/resume/',views.resume_file,name='resume'),
 path('applications/<int:pk>/decision/',views.decision,name='decision'),path('applications/<int:pk>/contact/',views.contact,name='contact'),path('applications/<int:pk>/github/',views.github,name='github'),
 path('applications/<int:pk>/interview/',views.interview_create,name='interview_create'),path('applications/<int:pk>/evaluate/',views.interview_evaluate,name='interview_evaluate'),
 path('interview/<uuid:token>/',views.interview_page,name='interview'),path('interview/<uuid:token>/api/',views.interview_api,name='interview_api'),path('applications/<int:pk>/feedback/',views.feedback,name='feedback'),
]
