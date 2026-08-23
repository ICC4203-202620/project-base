# Instalar la CA local en Android

Esta guía permite que Chrome y otras aplicaciones compatibles confíen en el
certificado HTTPS del entorno local. Antes de comenzar, prepara el computador
siguiendo la guía de [Linux](linux.md), [macOS](macos.md) o
[Windows](windows.md).

Los nombres y la ubicación de los menús pueden variar según la versión de
Android y el fabricante del dispositivo.

## Qué significa instalar la CA

El gateway nginx presenta `certs/local.pem`, un certificado X.509 firmado por
la CA local de `mkcert`. Android todavía no conoce esa CA, por lo que no puede
validar la firma. Al instalar `rootCA.pem`, agregas su certificado público al
almacén de confianza del usuario. Revisa el
[modelo completo de CA y certificados](../../README.md#conceptos-que-conviene-recordar)
si estos archivos te resultan nuevos.

Esta confianza es deliberadamente amplia: el dispositivo puede aceptar otros
certificados que esa CA firme. Por eso se usa solo en desarrollo y se elimina
al terminar. `mkcert` también advierte esta diferencia en sus
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

Puedes transferir `rootCA.pem` por USB, almacenamiento en la nube u otro canal
de confianza. Si el selector de archivos no muestra archivos `.pem`, crea una
copia llamada `rootCA.crt`; no cambies el archivo original. Guarda o descarga
la copia en el almacenamiento local del dispositivo antes de abrir el selector
de certificados.

## 3. Instala la CA

En versiones recientes de Android, la ruta suele ser:

1. Abre **Configuración**.
2. Entra en **Seguridad y privacidad**.
3. Abre **Más configuraciones de seguridad**.
4. Selecciona **Cifrado y credenciales**.
5. Elige **Instalar un certificado** y luego **Certificado de CA**.
6. Selecciona `rootCA.pem` o `rootCA.crt` y confirma la advertencia.

El dispositivo puede pedirte que configures o ingreses el PIN, patrón o
contraseña de bloqueo. Si la ruta es distinta, busca "certificado" o
"credenciales" dentro de Configuración.

> Selecciona específicamente **Certificado de CA**. **Certificado Wi-Fi** y
> **Certificado de usuario para VPN y aplicaciones** son categorías distintas
> y pueden exigir una clave privada. No las uses para confiar la CA HTTPS de
> este proyecto.

Un dispositivo administrado por una institución puede impedir que el usuario
agregue autoridades certificadoras. En ese caso no intentes evadir la política:
usa un dispositivo personal de desarrollo o consulta a su administrador.

## 4. Verifica desde Chrome

Conecta el teléfono a la misma red local que el computador y abre la URL con el
mismo host de acceso que incluiste en el certificado, por ejemplo:

```text
https://192.168.1.40:5173/healthz
```

Deberías ver una respuesta exitosa sin una advertencia de certificado. Si el
navegador indica que el nombre del certificado no coincide, vuelve a generarlo
incluyendo exactamente el host que aparece en la URL. Si elegiste el nombre
`.local` opcional, recuerda que
[mDNS solo funciona en el enlace local](../../README.md#ip-local-dns-y-mdns) y
que ese nombre exacto también debe estar en el certificado.

## 5. Aplicaciones Android nativas

Instalar la CA no garantiza que una aplicación nativa confíe en ella. Desde
Android 7, las aplicaciones que apuntan a API 24 o superior no confían de forma
predeterminada en las CA agregadas por el usuario. Para una aplicación de
desarrollo, habilita esta confianza solo en la configuración de depuración con
[Network Security Configuration](https://developer.android.com/privacy-and-security/security-config#TrustingDebugCa).

Esta distinción explica por qué una URL puede funcionar en Chrome y fallar en
una aplicación Android nativa. No incluyas la excepción en una compilación de
producción.

## 6. Quita la CA cuando termines

Vuelve a **Cifrado y credenciales**, abre las credenciales de usuario y elimina
la CA que instalaste. La ruta exacta puede variar según el dispositivo; evita
eliminar otras credenciales personales o institucionales.

Vuelve a la [documentación principal del backend](../../README.md).
