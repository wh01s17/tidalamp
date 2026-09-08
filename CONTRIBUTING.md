# Cómo contribuir

## Antes de nada: dos líneas que no se cruzan

1. **Nada de DRM.** `stream.py` rechaza los manifiestos cifrados en vez de
   descifrarlos, y no se descarga audio a disco. Los parches que añadan descifrado o
   descarga a fichero no se aceptan. No es una preferencia estética: es lo que mantiene
   el proyecto fuera de las leyes anti-elusión.
2. **Nada de credenciales incrustadas.** Ni claves de API, ni tokens, ni secretos de
   cliente propios en el repositorio.

## Poner en marcha el entorno

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Hacen falta `mpv` en el sistema. `cava` es opcional (espectro real) y `dbus-daemon`
también (sin él, la integración de MPRIS se salta sola en vez de fallar).

## Lo que tiene que pasar antes de un commit

```sh
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m pytest -q --cov
```

Las cuatro cosas están en CI. La cobertura tiene un suelo del 70 %, que es un suelo y
no un objetivo: existe para que un cambio que vacíe las pruebas falle en vez de pasar
en silencio.

`tidalamp/mpris.py` está excluido de mypy a propósito: sus anotaciones son firmas de
D-Bus (`"b"`, `"a{sv}"`), no tipos de Python, y ningún verificador puede leerlas. A
cambio, ese módulo tiene pruebas de contrato contra un bus real en
`tests/test_mpris.py`.

## Cómo se escriben las pruebas aquí

No tocan la red, ni TIDAL, ni el bus de sesión del usuario. Hay dobles para todo lo que
haga falta: `tests/fake_mpv.py` habla el IPC de verdad, `tests/fake_cava.py` emite
frames binarios, y la integración de MPRIS levanta su propio `dbus-daemon` temporal.

Cuando arregles un fallo, la prueba debería contar **qué se rompía**, no sólo qué hace
la función. Buena parte de las de este repo llevan el síntoma en el nombre o en el
docstring, y eso es deliberado.

## Documentación

- `README.md` es la documentación pública en inglés. `plan.md` sigue siendo el
  documento de traspaso en español para el mantenedor original.
- `plan.md` es el documento de traspaso: qué existe, qué está verificado y **con qué
  criterio se tomó cada decisión**. Si tomas una decisión de arquitectura, va ahí, con
  el motivo. Si pierdes una tarde con una trampa, va a §7, para que nadie la repita.
- `CHANGELOG.md` se actualiza en el mismo commit que el cambio.

## Mensajes de commit

En imperativo y explicando **por qué**, no sólo qué. Si el cambio nace de una medida,
el número va en el mensaje: es lo que permite discutirlo después.
