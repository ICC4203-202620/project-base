# Confiar la CA local en Chrome y Firefox

Esta guía permite abrir el entorno de desarrollo en
<https://localhost:5173> sin una advertencia de certificado. Se aplica a los
navegadores de escritorio. Para un teléfono o tablet, usa las guías de
[Android](android.md) o [iOS y iPadOS](ios.md).

## Qué instala `mkcert`

El comando `mkcert -install` crea una autoridad certificadora local e instala
su certificado público en los almacenes de confianza compatibles. Después, el
helper del proyecto emite `certs/local.pem` para `localhost`, `127.0.0.1`,
`::1` y las direcciones LAN o nombres mDNS indicados.

El navegador confía en la conexión solo si se cumplen ambas condiciones:

1. confía en la CA que firmó el certificado; y
2. la dirección de la URL aparece en el `subjectAltName` del certificado.

Instalar la CA no vuelve válido un certificado emitido para otro nombre. Tampoco
debes importar `certs/local.pem` como autoridad: el archivo que representa a la
CA es `rootCA.pem`, ubicado en el directorio que muestra `mkcert -CAROOT`.

> **Nunca instales ni compartas `rootCA-key.pem`.** Esa clave permite firmar
> nuevos certificados que tus dispositivos considerarían confiables.

## Instalación recomendada

Cierra Chrome y Firefox. Desde una terminal del mismo sistema operativo y con
el mismo usuario que abre los navegadores, ejecuta:

```console
mkcert -install
mkcert -CAROOT
```

El primer comando instala la CA; el segundo muestra dónde conserva
`rootCA.pem` y `rootCA-key.pem`. Reinicia los navegadores después de instalarla.
Las guías de [Linux](linux.md), [macOS](macos.md) y
[Windows](windows.md) indican cómo instalar `mkcert` y sus herramientas NSS.

## Google Chrome

Chrome de escritorio incorpora las CA personalizadas instaladas en el almacén
de certificados del sistema operativo. Por eso, normalmente `mkcert -install`
es suficiente y no se importa el certificado directamente en una página web.

Para comprobar el almacén que Chrome está usando:

1. abre **Configuración → Privacidad y seguridad → Seguridad**;
2. en **Opciones avanzadas**, selecciona **Gestionar certificados**; y
3. busca la CA local creada por `mkcert` entre las autoridades raíz confiables.

La pantalla exacta depende del sistema operativo y de la versión de Chrome. La
[documentación de seguridad de Chrome](https://support.google.com/chrome/answer/10468685?co=GENIE.Platform%3DDesktop&hl=es)
describe este comportamiento.

En Linux, instala primero las herramientas NSS señaladas en la
[guía de Linux](linux.md) y vuelve a ejecutar `mkcert -install`. `mkcert`
soporta tanto el almacén del sistema como los almacenes de Chrome y Chromium,
según estén disponibles.

## Mozilla Firefox

En Windows y macOS, las versiones actuales de Firefox confían automáticamente
en las CA de terceros instaladas en el sistema. En **Ajustes → Privacidad y
seguridad**, busca la sección **Conexión y seguridad del software**, abre sus
opciones avanzadas y comprueba en **Certificados** que esté activa la opción
**Permitir que Firefox confíe automáticamente en certificados raíz de terceros
que instales**. Mozilla documenta este mecanismo en
[Confiar automáticamente en certificados raíz de terceros](https://support.mozilla.org/kb/automatically-trust-third-party-certificates).

En macOS y Linux, `mkcert` también puede instalar directamente la CA en el
almacén NSS de Firefox. Para ello necesita `nss` o `certutil`; después de
instalarlos, vuelve a ejecutar `mkcert -install` y reinicia Firefox.

Si Firefox todavía muestra `SEC_ERROR_UNKNOWN_ISSUER`, importa manualmente solo
el certificado público de la CA:

1. ejecuta `mkcert -CAROOT` y ubica `rootCA.pem`;
2. abre **Ajustes → Privacidad y seguridad → Certificados**;
3. selecciona **Ver certificados → Autoridades → Importar**;
4. elige `rootCA.pem` y autorízalo para identificar sitios web; y
5. reinicia Firefox.

La importación afecta al perfil de Firefox donde la realizaste. Otro perfil
puede requerir su propia configuración.

## Levantar y verificar el entorno HTTPS

Copia `.env.local.example` como `.env.local`, genera el certificado y levanta
Compose según la guía de tu sistema operativo. Recuerda que Compose no carga
`.env.local` automáticamente: usa `--env-file .env.local`. El perfil publica
HTTPS en el puerto 5173:

```text
https://localhost:5173/
https://localhost:5173/healthz
https://localhost:5173/docs
```

El navegador debe mostrar una conexión segura y `/healthz` debe responder
`{"status":"ok"}`. Si aparece una advertencia:

- confirma que ejecutaste `mkcert -install` con el mismo usuario que abre el
  navegador;
- reinicia completamente el navegador;
- revisa que nginx esté presentando `certs/local.pem`;
- verifica que el certificado incluya `localhost`; y
- comprueba que la fecha y hora del computador sean correctas.

No uses la opción del navegador para ignorar permanentemente el error. Hacerlo
ocultaría una configuración incompleta y no demostraría que la PWA funciona en
un contexto HTTPS confiable.

Cuando ya no necesites esta CA de desarrollo, puedes retirarla de los almacenes
administrados por `mkcert`:

```console
mkcert -uninstall
```

Reinicia los navegadores después de retirarla. Si importaste `rootCA.pem`
manualmente en un perfil de Firefox, elimínalo también desde **Ver certificados
→ Autoridades** en ese perfil.

Referencias:

- [`mkcert`: CA local y almacenes compatibles](https://github.com/FiloSottile/mkcert#supported-root-stores)
- [Chrome: gestionar certificados del dispositivo](https://support.google.com/chrome/answer/10468685?co=GENIE.Platform%3DDesktop&hl=es)
- [Firefox: confiar en certificados raíz de terceros](https://support.mozilla.org/kb/automatically-trust-third-party-certificates)
