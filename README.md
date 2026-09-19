# 💸 Cuentas Claras

App sencilla en Django para dividir gastos en grupo y saber quién le debe a quién.

## Cómo correrla
```
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
Abre http://127.0.0.1:8000/

## Cómo funciona
1. Crea un grupo (ej: "Viaje a Villa de Leyva").
2. Agrega las personas.
3. Registra cada gasto y quién lo pagó.
4. La app divide en partes iguales y te muestra los pagos mínimos para quedar a mano.

Opcional: `python manage.py createsuperuser` para usar /admin/.
