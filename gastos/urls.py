from django.urls import path

from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('grupo/<int:grupo_id>/', views.grupo, name='grupo'),
    path('sugerencias/', views.sugerencias, name='sugerencias'),
    path('asistente/', views.asistente, name='asistente'),
    path('grupo/<int:grupo_id>/borrar/', views.borrar_grupo, name='borrar-grupo'),
    path('gasto/<int:gasto_id>/borrar/', views.borrar_gasto, name='borrar-gasto'),
]
