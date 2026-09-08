# Empaquetado

Dos canales que se complementan: el AUR para Arch, donde se puede declarar `mpv` como
dependencia real y `cava` como opcional, y PyPI para el resto de distribuciones Linux,
donde no se puede. Windows no es compatible y macOS no está soportado ni probado.

La guía completa, paso a paso, para preparar la versión, configurar PyPI, crear el
GitHub Release y publicar en el AUR está en [`../publish.md`](../publish.md). Este
archivo conserva el resumen y las decisiones específicas del empaquetado.

## Publicar una versión

1. Cerrar la sección «Sin publicar» de `CHANGELOG.md` con el número y la fecha.
2. Subir `version` en `pyproject.toml` y `pkgver` en `packaging/aur/PKGBUILD`.
3. Regenerar el `.SRCINFO`: `cd packaging/aur && makepkg --printsrcinfo > .SRCINFO`.
4. Commit, `git tag vX.Y.Z`, `git push --tags`.
5. El tag dispara `.github/workflows/release.yml`, que comprueba que el tag coincide
   con la versión del `pyproject.toml`, construye sdist y wheel, pasa `twine check` y
   publica en PyPI.
6. Actualizar el `sha256sums` del PKGBUILD (§AUR) y subirlo al AUR.

## PyPI (Trusted Publishing)

El workflow publica con OIDC de GitHub Actions, no con un token de larga vida. Antes
del primer `push --tags` hay que darlo de alta una sola vez:

- En PyPI → *Your projects* → *Publishing* → *Add a new pending publisher*:
  - PyPI Project Name: `tidalamp`
  - Owner: `wh01s17`
  - Repository name: `tidalamp`
  - Workflow name: `release.yml`
  - Environment name: `pypi`
- En GitHub → *Settings* → *Environments* → crear el entorno `pypi`.

Sin esos dos pasos el job `publish` falla con un error de OIDC, no con uno de
credenciales; es lo esperado.

## AUR

El `PKGBUILD` construye desde el tarball del tag en GitHub. Todas las dependencias
están en los repos oficiales (`extra`), así que no arrastra nada del AUR.

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
git clone ssh://aur@aur.archlinux.org/tidalamp.git aur-tidalamp
cp packaging/aur/{PKGBUILD,.SRCINFO} aur-tidalamp/
cd aur-tidalamp && git commit -am "tidalamp X.Y.Z" && git push
```

El AUR exige que `PKGBUILD` y `.SRCINFO` vayan en el mismo commit y que la raíz del
repositorio sea el propio `PKGBUILD`; por eso se copian, en vez de subir este
directorio tal cual.

## mpv no se instala con pip

Quien haga `pip install tidalamp` sin `mpv` en el sistema se encuentra un `MpvNotFound`
al arrancar. Por eso la descripción del paquete lo dice en la primera línea y el README
lo repite en la sección de instalación.
