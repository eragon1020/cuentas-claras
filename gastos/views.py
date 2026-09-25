import time

import requests
from django.conf import settings
from django.core.cache import cache
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

# Modelos que NO queremos elegir automáticamente aunque Groq los liste
# (no son de chat: son de audio, moderación, guardrails, etc.).
_PALABRAS_EXCLUIDAS = ('whisper', 'tts', 'guard', 'moderation', 'audio')


def _elegir_modelo_groq():
    """Le pregunta a Groq qué modelos de chat tiene disponibles AHORA MISMO
    para esta API key, y elige uno. Se cachea 1 hora para no golpear la
    API de listado en cada pregunta del usuario."""
    modelo = cache.get('groq_modelo_elegido')
    if modelo:
        return modelo

    respuesta = requests.get(
        'https://api.groq.com/openai/v1/models',
        headers={'Authorization': f'Bearer {settings.GROQ_API_KEY}'},
        timeout=15,
    )
    respuesta.raise_for_status()
    disponibles = [
        m['id'] for m in respuesta.json().get('data', [])
        if not any(palabra in m['id'].lower() for palabra in _PALABRAS_EXCLUIDAS)
    ]
    if not disponibles:
        raise ValueError('Groq no devolvió ningún modelo de chat disponible.')

    # Preferimos un modelo "versatile"/grande si existe; si no, el primero que haya.
    preferidos = [m for m in disponibles if 'versatile' in m or '70b' in m]
    modelo = (preferidos or disponibles)[0]
    cache.set('groq_modelo_elegido', modelo, 60 * 60)
    return modelo


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
    """Consume una IA externa (API de Groq) para responder preguntas
    sobre la problemática que resuelve la app: dividir gastos compartidos."""
    form = PreguntaForm(request.POST or None)
    context = {'form': form, 'respuesta': None, 'error': None}

    if request.method == 'POST' and form.is_valid():
        pregunta = form.cleaned_data['pregunta']
        if not settings.GROQ_API_KEY:
            context['error'] = (
                'El asistente no está configurado (falta GROQ_API_KEY).'
            )
        else:
            url = 'https://api.groq.com/openai/v1/chat/completions'
            reintentos = 3
            exito = False
            ultimo_error_saturacion = False
            try:
                modelo = _elegir_modelo_groq()
            except (requests.RequestException, ValueError) as exc:
                print(f'ERROR eligiendo modelo de Groq: {exc}')
                modelo = None

            if modelo is None:
                context['error'] = 'No se pudo consultar los modelos disponibles de Groq.'
            else:
                payload = {
                    'model': modelo,
                    'messages': [
                        {'role': 'system', 'content': PROMPT_SISTEMA_ASISTENTE},
                        {'role': 'user', 'content': pregunta},
                    ],
                    'max_tokens': 400,
                }
                for intento in range(1, reintentos + 1):
                    try:
                        respuesta = requests.post(
                            url,
                            headers={
                                'Authorization': f'Bearer {settings.GROQ_API_KEY}',
                                'content-type': 'application/json',
                            },
                            json=payload,
                            timeout=30,
                        )
                        respuesta.raise_for_status()
                        datos = respuesta.json()
                        opciones = datos.get('choices', [])
                        texto = ''
                        if opciones:
                            texto = opciones[0].get('message', {}).get('content', '')
                        context['respuesta'] = texto or 'No obtuve una respuesta del asistente.'
                        context['pregunta'] = pregunta
                        exito = True
                        break
                    except requests.RequestException as exc:
                        codigo = exc.response.status_code if exc.response is not None else None
                        detalle = f' [{codigo}] {exc.response.text[:300]}' if exc.response is not None else ''
                        print(f'ERROR al llamar a Groq con modelo "{modelo}" (intento {intento}):{detalle} | {exc}')
                        if codigo == 404:
                            # El modelo elegido dejó de existir justo ahora: invalidamos
                            # la caché para que la próxima pregunta elija otro.
                            cache.delete('groq_modelo_elegido')
                            context['error'] = 'El modelo de IA cambió, intenta de nuevo.'
                            break
                        saturado = codigo in (429, 503)
                        ultimo_error_saturacion = saturado
                        if saturado and intento < reintentos:
                            time.sleep(2 * intento)
                            continue
                        break

                if not exito and not context['error']:
                    if ultimo_error_saturacion:
                        context['error'] = (
                            'El modelo de IA está saturado en este momento. Intenta de nuevo en unos segundos.'
                        )
                    else:
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
