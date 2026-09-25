import requests
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import GastoForm, GrupoForm, MiembroForm, PreguntaForm
from .logic import calcular_pagos, calcular_saldos
from .models import Gasto, Grupo

# Contexto fijo que le da a la IA el "para qué" existe la app, para que
# responda siempre enfocada en la problemática que resuelve Cuentas Claras.
PROMPT_SISTEMA_ASISTENTE = (
    'Eres el asistente de "Cuentas Claras", una app web para dividir y '
    'controlar gastos compartidos entre grupos de personas (viajes, '
    'arriendos, salidas, etc.). La app permite crear grupos, agregar '
    'miembros, registrar gastos y calcular automáticamente cuánto le debe '
    'cada persona a cada otra para saldar las cuentas de forma justa. '
    'Responde SIEMPRE en español, de forma breve (máximo 4-5 líneas) y '
    'enfocado en ayudar al usuario a entender o resolver problemas de '
    'división de gastos compartidos, saldos entre personas, o el uso de '
    'esta aplicación. Si te preguntan algo totalmente ajeno a ese tema, '
    'redirige amablemente la conversación hacia la problemática de gastos '
    'compartidos que resuelve la app.'
)


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


def asistente(request):
    """Consume una IA externa (API de Google Gemini) para responder preguntas
    sobre la problemática que resuelve la app: dividir gastos compartidos."""
    form = PreguntaForm(request.POST or None)
    context = {'form': form, 'respuesta': None, 'error': None}

    if request.method == 'POST' and form.is_valid():
        pregunta = form.cleaned_data['pregunta']
        if not settings.GEMINI_API_KEY:
            context['error'] = (
                'El asistente no está configurado (falta GEMINI_API_KEY).'
            )
        else:
            try:
                url = (
                    'https://generativelanguage.googleapis.com/v1beta/models/'
                    'gemini-2.5-flash:generateContent'
                )
                respuesta = requests.post(
                    url,
                    headers={
                        'x-goog-api-key': settings.GEMINI_API_KEY,
                        'content-type': 'application/json',
                    },
                    json={
                        'system_instruction': {
                            'parts': [{'text': PROMPT_SISTEMA_ASISTENTE}]
                        },
                        'contents': [
                            {'role': 'user', 'parts': [{'text': pregunta}]}
                        ],
                    },
                    timeout=30,
                )
                respuesta.raise_for_status()
                datos = respuesta.json()
                candidatos = datos.get('candidates', [])
                texto = ''
                if candidatos:
                    partes = candidatos[0].get('content', {}).get('parts', [])
                    texto = ''.join(p.get('text', '') for p in partes)
                context['respuesta'] = texto or 'No obtuve una respuesta del asistente.'
                context['pregunta'] = pregunta    
                
            except requests.RequestException as exc:
                   detalle = ''
                  if exc.response is not None:
                    detalle = f' [{exc.response.status_code}] {exc.response.text[:300]}'
                print(f'ERROR al llamar a Gemini:{detalle} | {exc}')
                context['error'] = 'No se pudo conectar con el asistente de IA. Intenta de nuevo.'

    return render(request, 'gastos/asistente.html', context)


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
