# Conector Meta para Marketing Command Center

Módulo opcional para conectar páginas reales de Facebook al centro de mando de marketing.

## Configuración rápida

1. Instala `marketing_command_center` y después `marketing_command_center_meta`.
2. Asigna al usuario el grupo **Administrador del conector Meta**.
3. En **Marketing → Configuración → Meta / Facebook → Conexiones Meta**, crea una conexión.
4. Registra el ID de aplicación, el secreto y un token de usuario de Meta.
5. Pulsa **Probar conexión** y después **Descubrir páginas**.
6. Revisa las páginas encontradas y pulsa **Sincronizar páginas**.

## Flujo para una página real

En Meta for Developers crea o selecciona una aplicación, configura el producto
Pages y genera un token de usuario con acceso a las páginas que administras.
El token debe permitir consultar la identidad del usuario y las páginas; Meta
puede exigir revisión de permisos según el tipo de cuenta y el entorno. Pega el
token en Odoo y usa **Probar conexión**. Si todo está correcto, **Descubrir
páginas** trae todas las páginas disponibles para ese usuario y guarda un token
independiente por página.

No hace falta copiar el token de cada página manualmente cuando la respuesta de
Meta lo incluye. Para una página creada manualmente, registra su ID y su token
de página en el formulario **Páginas de Facebook**.

## Qué sincroniza

- Varias páginas por una misma conexión.
- Publicaciones del período configurado por página (1 a 365 días).
- Enlace, texto, fecha y métricas disponibles de cada publicación.
- En publicaciones de página: reacciones, comentarios y compartidos cuando el
  token y la versión de Graph los exponen. Si una métrica no está autorizada,
  la sincronización base continúa sin bloquearse.
- En la ficha de cada página: sitio web, descripción y el ID de Instagram
  Business vinculado cuando Meta lo devuelve.
- En publicaciones con adjuntos de video: clasificación automática como
  **Video** y conservación del enlace del adjunto cuando no existe permalink.
- Para Instagram se procesa el primer lote válido de hasta 100 medios, evitando
  que un cursor inválido de Graph descarte todo el lote y afecte a Facebook.
- Comentarios e interacciones con control de duplicados.
- Estado, fecha, conteo y detalle técnico en el chatter de la conexión y de la página.
- Sincronización programada cada seis horas, además del botón manual.

La consulta es incremental por ventana de días y es idempotente: repetirla
actualiza los mismos registros en lugar de crear duplicados.

## Permisos y seguridad

El grupo **Usuario del conector Meta** puede consultar las páginas. El grupo
**Administrador del conector Meta** puede guardar credenciales, probar,
descubrir y sincronizar. Los tokens no se muestran a usuarios normales y nunca
se escriben en el chatter ni en mensajes de marketing.

También puedes crear una página manualmente con su ID y token de página. Cada página queda vinculada a una cuenta Facebook del centro de mando base.

La sincronización actual es de lectura: guarda publicaciones, métricas disponibles e interacciones/comentarios. No publica, responde ni modifica contenido en Meta. La tarea programada se ejecuta cada seis horas y se puede ejecutar manualmente desde la conexión. Instagram, TikTok y otras redes deben conectarse mediante módulos independientes para conservar la modularidad.

## Resultado de la prueba real (03-09-2026)

La conexión configurada **SEMINUEVOS** respondió correctamente, descubrió 7
páginas y sincronizó 112 publicaciones con 179 comentarios. En una publicación
real se validó el acceso a `shares`, `comments.summary` y
`reactions.summary`. Las métricas avanzadas probadas (`post_clicks`,
`post_video_views` y `post_engaged_users`) fueron rechazadas por Graph para
este token/versión, por lo que no se solicitan en el flujo normal.

También se comprobó que la página expone `website`, `about` e
`instagram_business_account`. El campo `whatsapp_business_account` no existe
para esta versión de Graph/token y se deja fuera para no romper la consulta.

La prueba de Instagram sincronizó 101 medios reales de dos cuentas recientes,
101 métricas, 52 videos/reels y 170 comentarios, sin duplicados por ID externo.
La cuenta `patiotuerca_panama` quedó vinculada con 1.936 seguidores y 158
medios disponibles, pero sus medios más recientes entregados por Graph están
fuera de la ventana de 30 días configurada.
