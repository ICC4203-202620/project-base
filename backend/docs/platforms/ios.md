# Instalar la CA local en iOS o iPadOS

Esta guía permite que Safari y otras aplicaciones compatibles confíen en el
certificado HTTPS del entorno local. Antes de comenzar, prepara el computador
siguiendo la guía de [Linux](linux.md), [macOS](macos.md) o
[Windows](windows.md).

## Qué significa instalar la CA

El gateway nginx presenta `certs/local.pem`, un certificado X.509 firmado por
la CA local de `mkcert`. iOS todavía no conoce esa CA, por lo que no puede
validar la firma. Al instalar `rootCA.pem` y habilitar su confianza, agregas su
certificado público al almacén de confianza del dispositivo. Revisa el
[modelo completo de CA y certificados](../../README.md#conceptos-que-conviene-recordar)
si estos archivos te resultan nuevos.

Esta confianza es deliberadamente amplia: el dispositivo puede aceptar otros
certificados que esa CA firme. Por eso se usa solo en desarrollo y se elimina
al terminar. `mkcert` también describe este flujo en sus
[instrucciones para dispositivos móviles](https://github.com/FiloSottile/mkcert#mobile-devices).

## 1. Localiza la CA

En el computador donde ejecutaste `mkcert`, obtén su directorio:

```bash
mkcert -CAROOT
```

El archivo que debes transferir es `rootCA.pem`, el certificado público de la
CA. No necesitas copiar el certificado del servidor ni ninguna clave privada.

> Instala la CA solo en dispositivos de desarrollo. Nunca copies ni compartas
> `rootCA-key.pem`: es la clave privada que permite emitir certificados de
> confianza para esa CA.

## 2. Transfiere el certificado al dispositivo

Envía `rootCA.pem` mediante AirDrop, Archivos, correo u otro canal de confianza
y ábrelo en el dispositivo. El certificado de la CA es público, pero conviene
transferirlo de forma intencional para no confundirlo con otro perfil. Conserva
el archivo original en el computador.

## 3. Instala el perfil

Después de abrir el certificado:

1. Abre **Configuración**.
2. Selecciona **Perfil descargado**.
3. Toca **Instalar** e ingresa el código del dispositivo.
4. Confirma nuevamente con **Instalar**.

Si **Perfil descargado** no aparece, revisa **General > VPN y gestión de
dispositivos**. Apple describe este proceso en
[Instalar un perfil de configuración](https://support.apple.com/es-es/102400).
Apple elimina automáticamente un perfil pendiente si no lo instalas dentro de
ocho minutos; si ocurre, vuelve a abrir `rootCA.pem` y repite el proceso.

En versiones actuales de iOS, Protección del dispositivo en caso de robo puede
bloquear la instalación fuera de una ubicación habitual. Haz esta preparación
en una ubicación conocida y conserva las protecciones del dispositivo; no las
desactives sólo para completar el ejercicio.

Un dispositivo administrado por una institución puede impedir la instalación o
la modificación de confianza. En ese caso no intentes evadir la política: usa
un dispositivo personal de desarrollo o consulta a su administrador.

## 4. Habilita la confianza total

Instalar el perfil no basta para usarlo con HTTPS. Debes habilitar expresamente
la confianza de la CA:

1. Abre **Configuración > General > Información**.
2. Entra en **Configuración de confianza de certificados**.
3. Activa la confianza total para la CA de `mkcert`.
4. Confirma la advertencia.

Este paso adicional es necesario para certificados raíz instalados
manualmente, como explica Apple en
[Confiar en certificados instalados manualmente](https://support.apple.com/es-es/102390).
Instalar el perfil coloca el certificado en el dispositivo; habilitar la
confianza autoriza además su uso para validar conexiones TLS. Son dos decisiones
separadas.

## 5. Verifica desde Safari

Conecta el iPhone o iPad a la misma red local que el computador y abre la URL
con el mismo host de acceso que incluiste en el certificado, por ejemplo:

```text
https://192.168.1.40:5173/healthz
```

Deberías ver una respuesta exitosa sin una advertencia de certificado. Si
Safari indica que el nombre del certificado no coincide, vuelve a generarlo con
el host exacto que aparece en la URL. Si elegiste el nombre `.local` opcional,
recuerda que
[mDNS solo funciona en el enlace local](../../README.md#ip-local-dns-y-mdns) y
que ese nombre exacto también debe estar en el certificado.

## 6. Quita la CA cuando termines

Abre **Configuración > General > VPN y gestión de dispositivos**, selecciona el
perfil de la CA y toca **Eliminar perfil**. Elimina solo el perfil que instalaste
para este entorno de desarrollo.

Vuelve a la [documentación principal del backend](../../README.md).
