from django.urls import path
from . import views
urlpatterns=[
 path('',views.landing,name='home'),path('dashboard/',views.home,name='dashboard'),path('jobs/new/',views.job_create,name='job_create'),
 path('jobs/<int:pk>/setup/',views.job_setup,name='job_setup'),path('jobs/<int:pk>/',views.workspace,name='workspace'),path('jobs/<int:pk>/upload/',views.upload,name='upload'),
 path('applications/<int:pk>/',views.candidate_detail,name='candidate'),path('applications/<int:pk>/process/',views.process,name='process'),path('applications/<int:pk>/resume/',views.resume_file,name='resume'),
 path('applications/<int:pk>/decision/',views.decision,name='decision'),path('applications/<int:pk>/contact/',views.contact,name='contact'),path('applications/<int:pk>/github/',views.github,name='github'),
 path('applications/<int:pk>/interview-guide/generate/',views.guide_generate,name='guide_generate'),
 path('applications/<int:pk>/interview-guide/save/',views.guide_save,name='guide_save'),
 path('applications/<int:pk>/feedback/',views.feedback,name='feedback'),
]
