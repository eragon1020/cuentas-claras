import requests
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import GastoForm, GrupoForm, MiembroForm
from .logic import calcular_pagos, calcular_saldos
from .models import Gasto, Grupo


def inicio(request):
    # 1) La vista consume el MODELO...
    grupos = Grupo.objects.all()
    form = GrupoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        grupo = form.save()
        return redirect('grupo', grupo.id)
    # 2) ...arma el CONTEXT...
    context = {'grupos': grupos, 'form': form}
    # 3) ...y render() lo entrega al TEMPLATE.
    return render(request, 'gastos/inicio.html', context)


def grupo(request, grupo_id):
    # get_object_or_404: devuelve el objeto o responde 404 si no existe.
    g = get_object_or_404(Grupo, id=grupo_id)
    form_miembro = MiembroForm(prefix='m')
    form_gasto = GastoForm(grupo=g, prefix='g')

    if request.method == 'POST':
        if 'agregar_miembro' in request.POST:
            form_miembro = MiembroForm(request.POST, prefix='m')
            if form_miembro.is_valid():
                m = form_miembro.save(commit=False)
                m.grupo = g
                m.save()
                return redirect('grupo', g.id)
        elif 'agregar_gasto' in request.POST:
            form_gasto = GastoForm(request.POST, grupo=g, prefix='g')
            if form_gasto.is_valid():
                gasto = form_gasto.save(commit=False)
                gasto.grupo = g
                gasto.save()
                return redirect('grupo', g.id)

    saldos = calcular_saldos(g)
    context = {
        'grupo': g,
        'form_miembro': form_miembro,
        'form_gasto': form_gasto,
        'saldos': saldos.items(),
        'pagos': calcular_pagos(saldos),
        'total': sum(x.monto for x in g.gastos.all()),
    }
    return render(request, 'gastos/grupo.html', context)


def sugerencias(request):
    """Consume el microservicio propio (FastAPI + MongoDB Atlas)."""
    context = {'sugerencias': [], 'error': None, 'url': settings.MICROSERVICIO_URL}
    try:
        respuesta = requests.get(f'{settings.MICROSERVICIO_URL}/sugerencias', timeout=60)
        respuesta.raise_for_status()
        context['sugerencias'] = respuesta.json()
    except requests.RequestException:
        context['error'] = 'No se pudo conectar con el microservicio. Intenta de nuevo en un momento.'
    return render(request, 'gastos/sugerencias.html', context)


@require_POST
def borrar_gasto(request, gasto_id):
    gasto = get_object_or_404(Gasto, id=gasto_id)
    grupo_id = gasto.grupo_id
    gasto.delete()
    return redirect('grupo', grupo_id)


@require_POST
def borrar_grupo(request, grupo_id):
    get_object_or_404(Grupo, id=grupo_id).delete()
    return redirect('inicio')
