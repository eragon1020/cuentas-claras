# 💸 Cuentas Claras


antes de todo , toca levantar el microservicio , entrar a este link hasta que salga un archivo json en pantalla:

https://cuentas-claras-2iy4.onrender.com/sugerencias


 despues entrar a este Link de render  donde estara todo completo:

https://cuentas-claras-1.onrender.com/


esto se hace por que render duerme los microservicios, entonces toca levantarlo antes.

## 🤖 Asistente de IA (vista `/asistente/`)

Esta vista consulta una IA externa (Gemini, de Google) para responder
preguntas sobre la problemática que resuelve la app: dividir gastos
compartidos entre grupos de personas.

Para que funcione, define la variable de entorno `GEMINI_API_KEY` con tu
API key gratuita de Google AI Studio (https://aistudio.google.com/apikey):

```bash
export GEMINI_API_KEY="tu-api-key-aqui"
```

En Render, agrégala en la sección "Environment" del servicio web. Si la
variable no está configurada, la vista muestra un mensaje de error en vez
de fallar.
