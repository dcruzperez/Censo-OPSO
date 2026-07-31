# OPSO — Operativo Social

Sistema web para digitalizar el levantamiento de información de familias en
operativos sociales.

Proyecto de título · Ingeniería en Computación e Informática · Universidad
Andrés Bello.

**Stack:** Python 3.14 · Django 6.0 · PostgreSQL 18 · Bootstrap 5.3

---

## Estructura

```
stock-flow-main/
│
├── .venv/      entorno virtual (no se versiona; se reconstruye con requirements.txt)
├── OPSO/       prototipo HTML estático original (referencia de diseño)
└── backend/    ← PROYECTO DJANGO
```

El código, la documentación y las instrucciones detalladas están en
**[`backend/`](backend/README.md)**.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

cd backend
..\.venv\Scripts\python.exe scripts\preparar_base_datos.py --migrar
..\.venv\Scripts\python.exe manage.py runserver
```

`preparar_base_datos.py` crea la base y el usuario de PostgreSQL, genera una
contraseña aleatoria y la escribe en `.env`. Las historias de usuario y las
decisiones de diseño están en [`backend/README.md`](backend/README.md) y
[`backend/docs/`](backend/docs/).

## Pruebas

```bash
cd backend
set DB_ENGINE=sqlite3 && ..\.venv\Scripts\python.exe manage.py test
```

`DB_ENGINE=sqlite3` permite ejecutar las 546 pruebas sin un servidor
PostgreSQL levantado. Desarrollo y producción usan siempre PostgreSQL.
