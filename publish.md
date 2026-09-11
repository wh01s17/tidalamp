# Publicar tidalamp

Esta es la guía completa para crear una versión de tidalamp y publicarla en los tres
lugares que usa el proyecto:

1. **PyPI**, para instalarla con `pipx` o `pip` en distribuciones Linux.
2. **GitHub Releases**, como página pública de la versión y sus notas.
3. **AUR**, para instalarla en Arch Linux con todas sus dependencias del sistema.

El orden importa. Primero se prepara y valida el código, después se crea el tag —que
publica automáticamente en PyPI—, luego se crea el GitHub Release y finalmente se
calcula el checksum y, cuando vuelva a ser posible obtener una cuenta, se publica el
paquete en el AUR.

> [!IMPORTANT]
> **Estado a 2026-09-10:** hay siete versiones publicadas en PyPI, hasta `0.5.1`, con
> Trusted Publishing. El environment `pypi` de GitHub existe y el publisher de PyPI ya
> no está pendiente: se convirtió en uno normal con la primera publicación, así que
> §1.2 y §1.3 quedan como registro de cómo se configuró y no como pasos a repetir. La
> publicación en el AUR sigue aplazada por una causa externa:
> [el registro público de cuentas nuevas continúa cerrado](https://lists.archlinux.org/archives/list/aur-general%40lists.archlinux.org/message/2IJD5MFHSLXARQTOP4FH64CJLW2BIIGC/)
> durante el endurecimiento de seguridad posterior a
> [la oleada de paquetes maliciosos](https://lists.archlinux.org/archives/list/aur-general%40lists.archlinux.org/message/4JRS73YVTE7JUYHHE3ZDUIHXYHXZ3YQQ/).
> No se ha anunciado una fecha de reapertura y el mantenedor no tiene una cuenta
> anterior. Esto no bloquea PyPI ni GitHub Releases: el lanzamiento puede continuar
> por esos dos canales y completar el AUR más adelante.

Los ejemplos usan `0.1.0`, que fue la primera. En versiones posteriores hay que
sustituirlo por la que toque.

```sh
TIDALAMP_VERSION=0.1.0
TIDALAMP_TAG="v${TIDALAMP_VERSION}"
```

Mantén esas variables en la misma terminal durante todo el proceso.

## 1. Configuración inicial — sólo antes de la primera publicación

### 1.1. Permisos necesarios

La persona que publica necesita:

- permisos de escritura en `https://github.com/wh01s17/tidalamp`;
- una cuenta verificada en PyPI;
- una cuenta en el AUR y una clave SSH asociada;
- una máquina Arch Linux para probar y publicar el `PKGBUILD`.

No se necesita guardar un token de PyPI en GitHub. El workflow usa Trusted Publishing
con OIDC.

### 1.2. Crear el environment `pypi` en GitHub

**Completado el 2026-09-09.** El environment existe, exige la revisión manual de
`wh01s17`, no permite saltarse las reglas de protección y no contiene secretos. Los
pasos siguientes conservan la configuración exacta para poder auditarla o recrearla.

1. Abre `https://github.com/wh01s17/tidalamp`.
2. Entra en **Settings → Environments**.
3. Pulsa **New environment**.
4. Escribe exactamente `pypi` y pulsa **Configure environment**.
5. En las reglas de protección, añade al menos una persona en **Required reviewers**
   para que cada publicación necesite aprobación manual.
6. No añadas ningún secreto de PyPI.

La aprobación manual es una protección obligatoria para este flujo de publicación.
Si además se restringen las ramas y tags permitidos, hay que permitir tags con el
patrón `v*`; de lo contrario el job quedará bloqueado.

El nombre debe coincidir con `environment: pypi` en
`.github/workflows/release.yml`.

### 1.3. Registrar el pending publisher en PyPI

**Completado el 2026-09-09.** PyPI muestra el publisher pendiente con los cinco valores
de la tabla siguiente. Como `tidalamp` todavía no existe en PyPI, se conservará como
pendiente hasta que el workflow publique por primera vez:

1. Inicia sesión en `https://pypi.org/`.
2. Abre **Account settings → Publishing**.
3. En la sección de GitHub, pulsa **Add a new pending publisher**.
4. Completa los campos exactamente así:

   | Campo de PyPI | Valor |
   |---|---|
   | PyPI project name | `tidalamp` |
   | Owner | `wh01s17` |
   | Repository name | `tidalamp` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

5. Guarda el publisher.

Un pending publisher no crea el proyecto ni reserva su nombre. Conviene hacer este
paso inmediatamente antes de la primera publicación. Cuando el workflow publique por
primera vez, PyPI creará el proyecto y convertirá el publisher pendiente en uno normal.

### 1.4. Preparar la cuenta y la clave SSH del AUR

> [!WARNING]
> Este paso está bloqueado para quien no tenga ya una cuenta: el AUR mantiene cerrado
> el registro público de usuarios nuevos y no ofrece una cola de alta manual. Detente
> aquí y retoma esta sección sólo cuando el proyecto anuncie oficialmente la
> reapertura. No uses una cuenta ajena ni intentes eludir el cierre.

1. Crea o abre tu cuenta en `https://aur.archlinux.org/`.
2. Genera una clave dedicada para el AUR:

   ```sh
   ssh-keygen -t ed25519 -f ~/.ssh/aur
   ```

3. Copia el contenido de `~/.ssh/aur.pub` en **My Account → SSH Public Key** dentro
   del AUR.
4. Añade esta entrada a `~/.ssh/config`:

   ```sshconfig
   Host aur.archlinux.org
     IdentityFile ~/.ssh/aur
     User aur
   ```

5. Comprueba la autenticación:

   ```sh
   ssh -T aur@aur.archlinux.org
   ```

El AUR publica el nombre y correo configurados en los commits. Si no quieres usar tu
identidad global, configura otra localmente en el clon del AUR antes de crear el primer
commit.

### 1.5. Herramientas locales

El entorno Python de desarrollo necesita el proyecto y sus extras:

```sh
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]" build twine
```

En Arch, las herramientas del paquete se instalan con:

```sh
sudo pacman -S --needed base-devel pacman-contrib namcap git
```

`updpkgsums` pertenece a `pacman-contrib`. `gh`, la CLI de GitHub, es opcional; todos
sus pasos tienen una alternativa desde la web.

## 2. Elegir la versión

tidalamp sigue versionado semántico `MAJOR.MINOR.PATCH`:

- incrementa `PATCH` para correcciones compatibles, por ejemplo `0.1.0 → 0.1.1`;
- incrementa `MINOR` para funcionalidad nueva compatible, por ejemplo `0.1.1 → 0.2.0`;
- incrementa `MAJOR` cuando haya cambios incompatibles en una versión estable.

Antes de usar una versión, confirma que no existe como tag ni en PyPI:

```sh
git fetch origin --tags
git tag --list "$TIDALAMP_TAG"
```

El segundo comando no debe imprimir nada. Comprueba también
`https://pypi.org/project/tidalamp/`. PyPI no permite reemplazar los archivos de una
versión que ya fue publicada.

## 3. Preparar el repositorio

### 3.1. Partir de `main` actualizado y limpio

```sh
git switch main
git pull --ff-only origin main
git status --short
```

`git status --short` debe quedar vacío. No mezcles una publicación con cambios que no
pertenezcan a esa versión.

### 3.2. Actualizar los números de versión

La versión vive en **cinco** sitios. `release.yml` sólo compara el tag con el primero,
y `tests/test_about.py::test_every_copy_of_the_version_agrees` ata los otros dos que
son de Python: si alguno se queda atrás, la suite falla antes de llegar al tag. Los dos
últimos —el `?v=` del README y el `PKGBUILD`— no los comprueba nadie más que esta
sección.

1. En `pyproject.toml`:

   ```toml
   version = "0.1.0"
   ```

2. En `tidalamp/__init__.py`:

   ```python
   __version__ = "0.1.0"
   ```

   Es el respaldo de `about.version()` cuando no hay metadata instalada, y lo que ve
   quien ejecuta desde un checkout.

3. En `tidalamp/about.py`, la entrada correspondiente de `releases()`: el número, la
   fecha —que hasta la publicación dice «sin publicar»— y las notas de la versión.
   Es lo que muestra «Cambios por versión» en la pantalla de ayuda (`?`).

   ```python
   def releases() -> tuple[Release, ...]:
       return (
           Release(
               "0.1.0",
               "2026-09-15",
               (
                   _("…"),
                   _("…"),
               ),
           ),
       )
   ```

   Va aquí y no leído de `CHANGELOG.md` a propósito: ese fichero no viaja dentro del
   wheel, así que la pantalla saldría vacía para todo el que instale el paquete.

4. En `README.md`, el `?v=` de las URLs de `img/`:

   ```sh
   sed -i -E 's/\?v=[0-9.]+(["\)])/?v='"$TIDALAMP_VERSION"'\1/g' README.md
   rg -c 'v=' README.md   # cuenta las URLs; compárala con las que quedaron sin tocar
   ```

   Las dos clases de enlace tienen que entrar: las de `<img src="...">`, que
   acaban en comilla, y las de `![alt](...)` de Markdown, que acaban en
   paréntesis. Una expresión que solo contemple la comilla deja el banner de la
   cabecera anclado a la versión anterior, que es justo la imagen que más se ve.

   Las imágenes se enlazan por URL absoluta porque PyPI no resuelve rutas
   relativas, y esa URL no cambia cuando el fichero sí: el proxy de imágenes de
   GitHub sigue sirviendo la copia anterior durante horas. El token de versión es
   lo que la invalida. Si en esta versión no cambió ninguna imagen, da igual
   actualizarlo.

5. En `packaging/aur/PKGBUILD`:

   ```sh
   pkgver=0.1.0
   pkgrel=1
   ```

`pkgrel` vuelve a `1` cada vez que cambia `pkgver`. Si sólo se corrige el empaquetado
del AUR sin publicar una versión nueva de la aplicación, se conserva `pkgver` y se
incrementa únicamente `pkgrel`.

### 3.3. Cerrar el changelog

El `CHANGELOG.md` está **en inglés**, como el README y las notas de los releases: es lo
que lee alguien de fuera. Conserva una sección vacía para cambios futuros y mueve las
notas actuales bajo la versión y la fecha de publicación:

```markdown
## [Unreleased]

## [0.1.0] - YYYY-MM-DD

### Added

...
```

Los encabezados son los de Keep a Changelog en inglés: `Added`, `Changed`, `Deprecated`,
`Removed`, `Fixed`, `Security`.

Revisa que las notas describan sólo cambios incluidos en el commit que se etiquetará, y
que el resumen de `about.releases()` (paso 3.2) diga lo mismo en corto: son dos textos
para dos públicos —el changelog completo y las cuatro líneas que caben en la pantalla
de ayuda— y no deben contradecirse.

### 3.4. Regenerar `.SRCINFO`

```sh
cd packaging/aur
makepkg --printsrcinfo > .SRCINFO
cd ../..
```

Antes del primer tag es normal que todavía diga `sha256sums = SKIP`. El hash definitivo
se añadirá en la sección del AUR, cuando GitHub ya pueda generar el tarball del tag.

## 4. Validar la versión antes de etiquetarla

### 4.1. Calidad y pruebas

Ejecuta todas las comprobaciones desde la raíz del repositorio:

```sh
.venv/bin/ruff check tidalamp tests
.venv/bin/ruff format --check tidalamp tests
.venv/bin/mypy tidalamp
.venv/bin/python -m pytest -q
git diff --check
```

No continúes si alguna falla.

### 4.2. Construir y revisar los artefactos

Usa un directorio temporal nuevo para no validar por accidente archivos de una versión
anterior:

```sh
TIDALAMP_BUILD_DIR="$(mktemp -d)"
.venv/bin/python -m build --outdir "$TIDALAMP_BUILD_DIR"
.venv/bin/python -m twine check "$TIDALAMP_BUILD_DIR"/*
ls -lh "$TIDALAMP_BUILD_DIR"
```

Deben existir exactamente un `sdist` (`.tar.gz`) y un wheel (`.whl`) de la versión
elegida, y ambos deben pasar `twine check`.

Comprueba además que el wheel se instala en un entorno vacío:

```sh
TIDALAMP_TEST_VENV="$(mktemp -d)"
python -m venv "$TIDALAMP_TEST_VENV"
"$TIDALAMP_TEST_VENV/bin/pip" install "$TIDALAMP_BUILD_DIR"/tidalamp-*.whl
"$TIDALAMP_TEST_VENV/bin/tidalamp" --help
```

Esta comprobación no instala `mpv`; `tidalamp --help` no lo necesita. La reproducción
real sí requiere `mpv` instalado en el sistema.

## 5. Crear y subir el commit de la versión

Revisa todas las diferencias antes de confirmar:

```sh
git diff
git diff --check
git status --short
```

Añade los archivos de la versión, crea el commit y sube `main`:

```sh
git add \
  CHANGELOG.md \
  README.md \
  pyproject.toml \
  tidalamp/__init__.py \
  tidalamp/about.py \
  packaging/aur/PKGBUILD \
  packaging/aur/.SRCINFO
git commit -m "chore(release): prepare ${TIDALAMP_TAG}"
git push origin main
```

Esos siete nombres cubren todas las copias de la versión, la fecha y las notas, además
del paquete del AUR. Si la versión también contiene otros archivos ya revisados, deben
incluirse en el commit correspondiente antes de crear el tag.

En GitHub, abre **Actions → CI** y espera a que el commit de `main` termine en verde.
No crees el tag sobre un commit cuyo CI no haya finalizado correctamente.

## 6. Crear el tag y publicar en PyPI

### 6.1. Comprobación final

Antes de crear el tag, confirma:

- que el environment `pypi` existe en GitHub;
- que el pending publisher de PyPI usa exactamente los cinco valores de la sección
  1.3;
- que `main` está sincronizado y limpio;
- que la versión de `pyproject.toml` es idéntica al tag sin la `v`.

```sh
git status --short --branch
git log -1 --oneline
rg '^version = ' pyproject.toml
rg '^pkgver=' packaging/aur/PKGBUILD
```

### 6.2. Crear y subir sólo el tag deseado

```sh
git tag -a "$TIDALAMP_TAG" -m "tidalamp ${TIDALAMP_VERSION}"
git show --no-patch "$TIDALAMP_TAG"
git push origin "$TIDALAMP_TAG"
```

Evita `git push --tags`: podría subir tags locales que no pretendías publicar.

### 6.3. Vigilar el workflow

El push dispara `.github/workflows/release.yml`. Ese workflow:

1. comprueba que `vX.Y.Z` coincide con `project.version`;
2. construye el sdist y el wheel;
3. ejecuta `twine check`;
4. guarda los paquetes como artefacto de GitHub Actions;
5. obtiene una identidad OIDC y publica en PyPI sin token permanente.

Desde la web, abre **Actions → release → ejecución de `vX.Y.Z`**. Si el environment
requiere aprobación, aprueba el job `publish` cuando aparezca como pendiente.

Con GitHub CLI se puede consultar y seguir la ejecución:

```sh
gh run list --workflow release.yml --limit 5
gh run watch ID_DE_LA_EJECUCION
```

No continúes con el anuncio ni con el AUR hasta que los jobs `build` y `publish` estén
en verde.

### 6.4. Verificar PyPI desde cero

Abre `https://pypi.org/project/tidalamp/` y confirma la versión, descripción, README,
licencia, versión mínima de Python y enlaces del proyecto.

Prueba lo que recibirá un usuario, descargándolo desde PyPI en otro entorno vacío:

```sh
TIDALAMP_PYPI_VENV="$(mktemp -d)"
python -m venv "$TIDALAMP_PYPI_VENV"
"$TIDALAMP_PYPI_VENV/bin/pip" install "tidalamp[art]==${TIDALAMP_VERSION}"
"$TIDALAMP_PYPI_VENV/bin/tidalamp" --help
```

## 7. Crear el GitHub Release

El tag y el Release no son lo mismo. El tag ya existe y publicó PyPI; ahora se crea una
página pública con las notas de la versión. GitHub añadirá automáticamente descargas
`.zip` y `.tar.gz` del código correspondiente al tag.

### 7.1. Desde la web

1. Abre `https://github.com/wh01s17/tidalamp/releases`.
2. Pulsa **Draft a new release**.
3. En **Choose a tag**, selecciona el tag que ya se publicó: `vX.Y.Z`.
4. Usa como título `tidalamp X.Y.Z`.
5. Copia las notas de esa versión desde `CHANGELOG.md`, que ya está en inglés, o
   pulsa **Generate release notes** y revísalas manualmente. No dejes las notas en
   español: todos los releases publicados están en inglés y el enlace «Full changelog»
   de cada uno lleva a un fichero en inglés.
6. Marca **Set as the latest release**.
7. Marca **This is a pre-release** sólo si quieres presentar explícitamente esa versión
   como preliminar.
8. Pulsa **Publish release**.

No crees un tag diferente desde el formulario: el Release debe apuntar exactamente al
tag que activó la publicación de PyPI.

### 7.2. Con GitHub CLI

Para generar notas desde los commits:

```sh
gh release create "$TIDALAMP_TAG" \
  --verify-tag \
  --title "tidalamp ${TIDALAMP_VERSION}" \
  --generate-notes
```

Si preparaste las notas en un archivo, sustituye `--generate-notes` por
`--notes-file RUTA_AL_ARCHIVO`.

### 7.3. Adjuntar wheel y sdist — opcional

PyPI ya hospeda los paquetes y GitHub ya ofrece el código fuente. Si también quieres
que el wheel y el sdist aparezcan como assets del Release:

```sh
gh run download ID_DE_LA_EJECUCION \
  --name dist \
  --dir "dist/release-${TIDALAMP_VERSION}"
gh release upload "$TIDALAMP_TAG" "dist/release-${TIDALAMP_VERSION}"/*
```

El AUR no necesita estos assets: usa el tarball automático del tag.

## 8. Finalizar y publicar el paquete AUR

Esta sección se ejecuta en Arch Linux después de que el tag sea público.

El cierre del registro no impide ejecutar §8.1–§8.3: se puede calcular el checksum,
probar el paquete localmente y guardar esos metadatos en el repositorio principal. Sin
una cuenta anterior del AUR, §8.4–§8.6 quedan en pausa hasta que se reabra el registro.
PyPI y el GitHub Release no tienen que esperar al AUR.

### 8.1. Calcular el checksum definitivo

Actualiza `main` y entra al directorio del paquete:

```sh
git switch main
git pull --ff-only origin main
cd packaging/aur
updpkgsums
makepkg --printsrcinfo > .SRCINFO
```

Comprueba que ni `PKGBUILD` ni `.SRCINFO` conserven `SKIP`:

```sh
rg '^[[:space:]]*sha256sums' PKGBUILD .SRCINFO
```

Las líneas encontradas deben contener un hash SHA-256 real, no `SKIP`.

### 8.2. Construir, ejecutar los tests e instalar localmente

```sh
makepkg -Csi
namcap PKGBUILD
namcap tidalamp-*.pkg.tar.zst
tidalamp --help
pacman -Qi tidalamp
```

`makepkg -Csi` limpia restos de compilaciones anteriores, instala las dependencias,
construye el paquete, ejecuta `check()` e instala el resultado. Revisa todos los avisos
de `namcap`; algunos pueden ser informativos, pero no publiques con errores reales de
dependencias, rutas o metadatos.

### 8.3. Guardar el checksum en el repositorio principal

`updpkgsums` cambia archivos después del tag porque el tarball no existía antes. Guarda
el resultado en `main`; no muevas el tag:

```sh
cd ../..
git add packaging/aur/PKGBUILD packaging/aur/.SRCINFO
git commit -m "build(aur): finalize ${TIDALAMP_TAG} checksum"
git push origin main
```

Es correcto que este commit sea posterior al tag. El AUR recibe el `PKGBUILD` nuevo,
pero el código de la aplicación continúa siendo exactamente el del tag.

### 8.4. Crear el repositorio del paquete en el AUR

El repositorio AUR debe estar separado del repositorio principal. Desde la raíz de
tidalamp:

```sh
TIDALAMP_AUR_DIR="../aur-tidalamp"
git -c init.defaultBranch=master clone \
  ssh://aur@aur.archlinux.org/tidalamp.git \
  "$TIDALAMP_AUR_DIR"
```

En la primera publicación es normal recibir el aviso de que el repositorio está vacío.
El AUR sólo acepta pushes a la rama `master`.

Si el clon ya existe de una publicación anterior, no lo vuelvas a clonar:

```sh
TIDALAMP_AUR_DIR="../aur-tidalamp"
git -C "$TIDALAMP_AUR_DIR" pull --ff-only origin master
```

### 8.5. Copiar, revisar y subir `PKGBUILD` y `.SRCINFO`

```sh
cp packaging/aur/PKGBUILD "$TIDALAMP_AUR_DIR/PKGBUILD"
cp packaging/aur/.SRCINFO "$TIDALAMP_AUR_DIR/.SRCINFO"
git -C "$TIDALAMP_AUR_DIR" add PKGBUILD .SRCINFO
git -C "$TIDALAMP_AUR_DIR" diff --cached
git -C "$TIDALAMP_AUR_DIR" commit -m "tidalamp ${TIDALAMP_VERSION}"
git -C "$TIDALAMP_AUR_DIR" push origin master
```

`PKGBUILD` y `.SRCINFO` deben estar en el mismo commit. No subas el repositorio
principal completo al AUR.

### 8.6. Verificar el AUR

1. Abre `https://aur.archlinux.org/packages/tidalamp`.
2. Comprueba versión, `pkgrel`, descripción, URL, licencia, dependencias y checksum.
3. En una instalación limpia o después de eliminar la copia local, comprueba el flujo
   normal de usuario:

   ```sh
   yay -S tidalamp
   tidalamp --help
   ```

## 9. Lista final antes de anunciar la versión

- [ ] `CHANGELOG.md` contiene `X.Y.Z` y la fecha correcta.
- [ ] `pyproject.toml`, `tidalamp/__init__.py`, `tidalamp/about.py`, `PKGBUILD` y
      `.SRCINFO` muestran la misma versión (§3.2). La suite lo comprueba para los tres
      primeros; `.SRCINFO` no lo cubre nadie más que esta casilla.
- [ ] La pantalla de ayuda (`?`) muestra la versión y sus notas, y la fecha ya no dice
      «sin publicar».
- [ ] Las pruebas, Ruff, mypy, build y `twine check` pasan.
- [ ] El CI del commit de versión está en verde.
- [ ] Existe el tag anotado `vX.Y.Z` y apunta al commit correcto.
- [ ] El workflow `release` terminó con `build` y `publish` en verde.
- [ ] PyPI muestra la versión y una instalación nueva funciona.
- [ ] Existe un GitHub Release publicado sobre el mismo tag.
- [ ] El `PKGBUILD` usa un checksum real, nunca `SKIP`.
- [ ] `makepkg -Csi` y `namcap` fueron revisados.
- [ ] El AUR muestra la versión y una instalación mediante `yay` funciona.

## 10. Problemas frecuentes y recuperación

### El workflow dice que el tag no coincide con `pyproject.toml`

El tag `vX.Y.Z` y `project.version = "X.Y.Z"` deben ser idénticos. No muevas ni
reutilices un tag que ya haya sido publicado o consumido. La opción segura es corregir
los archivos y publicar una versión nueva.

### PyPI responde `invalid-pending-publisher` o `invalid-publisher`

Compara carácter por carácter owner, repositorio, nombre del workflow y environment.
Los errores más comunes son escribir `.github/workflows/release.yml` donde PyPI pide
sólo `release.yml`, o no usar `pypi` en ambos lados.

### El job `publish` queda esperando

Abre la ejecución en GitHub Actions. Si el environment exige revisión, aprueba el
deployment. Revisa también que sus reglas permitan tags `v*`.

### PyPI dice que el archivo o la versión ya existe

Una versión de PyPI es inmutable: no se puede sobrescribir. Incrementa la versión,
actualiza changelog y paquete AUR, crea un commit y tag nuevos y repite el proceso.

### `updpkgsums` o `makepkg` no descargan el tarball

Confirma que el tag sea público y que esta URL responda:

```text
https://github.com/wh01s17/tidalamp/archive/refs/tags/vX.Y.Z.tar.gz
```

Luego verifica que `pkgver` y la URL `source` del `PKGBUILD` formen exactamente ese
tag.

### El push al AUR falla

Comprueba:

- que la clave pública esté en tu perfil del AUR;
- que `ssh -T aur@aur.archlinux.org` te reconozca;
- que el remoto sea `ssh://aur@aur.archlinux.org/tidalamp.git`;
- que la rama sea `master`;
- que el commit incluya juntos `PKGBUILD` y `.SRCINFO`.

### El registro de una cuenta nueva en el AUR no está disponible

No es un fallo de tidalamp ni de la red local. El AUR cerró temporalmente el registro
público como parte de su respuesta de seguridad y no admite solicitudes manuales de
alta. Conserva preparado el paquete, sigue los anuncios de `aur-general` y retoma
§1.4 y §8.4–§8.6 sólo cuando Arch comunique la reapertura. No automatices reintentos ni
uses credenciales de otra persona.

### Se descubre un fallo grave después de publicar

No reemplaces el tag ni intentes sobrescribir PyPI. Corrige el fallo, incrementa la
versión PATCH y publica una nueva versión. Si el paquete defectuoso no debe instalarse,
márcalo como *yanked* en PyPI y explica la sustitución en GitHub y en el AUR.

## 11. Publicaciones posteriores

Para la segunda versión y las siguientes no se repite la configuración de PyPI ni el
GitHub environment. Tampoco se repite la clave SSH del AUR una vez que sea posible
crear la cuenta y completar esa configuración. El ciclo normal es:

1. elegir una versión nueva;
2. actualizar changelog, los cuatro sitios de la versión (§3.2: `pyproject.toml`,
   `tidalamp/__init__.py`, `releases()` en `tidalamp/about.py`, y `pkgver` con
   `pkgrel=1` en el `PKGBUILD`);
3. validar y construir;
4. confirmar el commit y esperar el CI;
5. crear y subir el tag;
6. verificar PyPI;
7. crear el GitHub Release;
8. recalcular el checksum, probar y actualizar el AUR.

Una corrección exclusiva del `PKGBUILD` no necesita versión nueva de PyPI ni nuevo
GitHub Release: incrementa sólo `pkgrel`, regenera `.SRCINFO`, prueba y publica el
commit en el AUR.

## Referencias oficiales

- [PyPI: crear un proyecto mediante un Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPI: publicar con Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [PyPI: solución de problemas de Trusted Publishing](https://docs.pypi.org/trusted-publishers/troubleshooting/)
- [GitHub: administrar Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
- [GitHub: administrar environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
- [ArchWiki: pautas de publicación en el AUR](https://wiki.archlinux.org/title/AUR_submission_guidelines)
- [AUR: cierre inicial por paquetes maliciosos](https://lists.archlinux.org/archives/list/aur-general%40lists.archlinux.org/message/4JRS73YVTE7JUYHHE3ZDUIHXYHXZ3YQQ/)
- [AUR: estado del servicio y registro aún cerrado](https://lists.archlinux.org/archives/list/aur-general%40lists.archlinux.org/message/2IJD5MFHSLXARQTOP4FH64CJLW2BIIGC/)
