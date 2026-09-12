# Empaquetado

Dos canales que se complementan: el AUR para Arch, donde se puede declarar `mpv` como
dependencia real y `cava` como opcional, y PyPI para el resto de distribuciones Linux,
donde no se puede. Windows no es compatible y macOS no está soportado ni probado.

> [!IMPORTANT]
> **PyPI está en marcha:** todas las versiones hasta `0.8.1` se publicaron mediante
> Trusted Publishing, sin ningún token de larga vida. El `PKGBUILD` del AUR
> sigue preparado y sin publicar, porque
> [el registro de cuentas nuevas sigue cerrado](https://lists.archlinux.org/archives/list/aur-general%40lists.archlinux.org/message/2IJD5MFHSLXARQTOP4FH64CJLW2BIIGC/)
> durante el endurecimiento de seguridad del servicio y no se ha anunciado una fecha
> de reapertura.

La guía completa, paso a paso, para preparar la versión, configurar PyPI, crear el
GitHub Release y publicar en el AUR está en [`../publish.md`](../publish.md). Este
archivo conserva el resumen y las decisiones específicas del empaquetado.

## Publicar una versión

1. Cerrar la sección `[Unreleased]` de `CHANGELOG.md` con el número y la fecha.
2. Actualizar la versión en los **cinco** sitios: `pyproject.toml`,
   `tidalamp/__init__.py`, la entrada de `releases()` en `tidalamp/about.py`, el `?v=`
   de las URLs de imagen del `README.md` y `pkgver` en `packaging/aur/PKGBUILD`; al
   cambiar `pkgver`, devolver `pkgrel` a `1`. El detalle está en `publish.md` §3.2.
3. Regenerar el `.SRCINFO`: `cd packaging/aur && makepkg --printsrcinfo > .SRCINFO`.
4. Crear el commit, un tag anotado con `git tag -a vX.Y.Z -m "tidalamp X.Y.Z"` y
   subir únicamente ese tag con `git push origin vX.Y.Z`.
5. El tag dispara `.github/workflows/release.yml`, que comprueba que el tag coincide
   con la versión del `pyproject.toml`, construye sdist y wheel, pasa `twine check` y
   publica en PyPI.
6. Actualizar el `sha256sums` del PKGBUILD (§AUR) y, cuando el registro vuelva a estar
   disponible, subirlo al AUR.

## PyPI (Trusted Publishing)

**Configurado el 2026-09-09.** El workflow publica con OIDC de GitHub Actions, no con
un token de larga vida. La configuración actual, que sólo se realiza una vez, es:

- En PyPI → *Your projects* → *Publishing* → *Add a new pending publisher*:
  - PyPI Project Name: `tidalamp`
  - Owner: `wh01s17`
  - Repository name: `tidalamp`
  - Workflow name: `release.yml`
  - Environment name: `pypi`
- En GitHub → *Settings* → *Environments* → crear el entorno `pypi`, con al menos una
  persona en **Required reviewers** para aprobar manualmente cada publicación.

Si se elimina alguno de esos dos elementos, el job `publish` fallará con un error de
OIDC, no con uno de credenciales.

## AUR

El `PKGBUILD` construye desde el tarball del tag en GitHub. Todas las dependencias
están en los repos oficiales (`extra`), así que no arrastra nada del AUR.

La receta siguiente permanece lista para la primera publicación. Como el mantenedor
no tiene una cuenta anterior y el alta pública continúa cerrada, se puede preparar y
probar el paquete localmente, pero no clonar ni enviar todavía el repositorio AUR. No
hay un procedimiento alternativo legítimo: hay que esperar el anuncio oficial de
reapertura.

`sha256sums` está como `SKIP` porque hasta que existe el tag no hay tarball que
resumir. Con el tag publicado:

```sh
cd packaging/aur
updpkgsums          # rellena sha256sums con el hash real
makepkg --printsrcinfo > .SRCINFO
makepkg -si         # prueba local: construye, corre los tests e instala
namcap PKGBUILD tidalamp-*.pkg.tar.zst
```

Y para subirlo, con el repositorio del AUR clonado aparte:

```sh
TIDALAMP_AUR_DIR="../aur-tidalamp"
git -c init.defaultBranch=master clone \
  ssh://aur@aur.archlinux.org/tidalamp.git \
  "$TIDALAMP_AUR_DIR"
cp packaging/aur/PKGBUILD "$TIDALAMP_AUR_DIR/PKGBUILD"
cp packaging/aur/.SRCINFO "$TIDALAMP_AUR_DIR/.SRCINFO"
git -C "$TIDALAMP_AUR_DIR" add PKGBUILD .SRCINFO
git -C "$TIDALAMP_AUR_DIR" diff --cached
git -C "$TIDALAMP_AUR_DIR" commit -m "tidalamp X.Y.Z"
git -C "$TIDALAMP_AUR_DIR" push origin master
```

El AUR exige que `PKGBUILD` y `.SRCINFO` vayan en el mismo commit y que la raíz del
repositorio sea el propio `PKGBUILD`; por eso se copian, en vez de subir este
directorio tal cual.

## mpv no se instala con pip

Quien haga `pip install tidalamp` sin `mpv` en el sistema se encuentra un `MpvNotFound`
al arrancar. Por eso la descripción del paquete lo dice en la primera línea y el README
lo repite en la sección de instalación.
