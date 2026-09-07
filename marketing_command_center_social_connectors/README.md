# Conectores sociales avanzados

Módulo opcional para medir Instagram, YouTube, LinkedIn y TikTok desde el
Centro de mando de marketing. Facebook se mantiene en el módulo independiente
`marketing_command_center_meta` porque Instagram comparte parte de la API de
Meta, pero ambos módulos pueden instalarse juntos.

## Configuración

1. Instala `marketing_command_center` y este módulo.
2. Asigna **Administrador de conectores sociales** al usuario.
3. Abre **Marketing → Configuración → Conectores sociales → Conexiones sociales**.
4. Elige la red, pega el token OAuth o API key correspondiente y pulsa **Probar conexión**.
5. Pulsa **Descubrir cuentas** y después **Sincronizar cuentas**.

La conexión puede descubrir varias cuentas cuando el proveedor lo permite. Para
YouTube puedes indicar el ID del canal si usas API key. Para LinkedIn puedes
indicar el ID de organización; sin ese dato se valida el perfil OAuth personal.

## Datos medidos

- Publicaciones, vídeos o contenido disponible en la API oficial.
- Seguidores/suscriptores cuando el proveedor lo devuelve.
- Alcance, impresiones, reproducciones, me gusta, comentarios y compartidos
  según la red y los permisos concedidos.
- Comentarios disponibles, con deduplicación e historial en el Centro de mando.
- Fecha, estado, conteo y detalle de cada sincronización en el chatter.

La sincronización es de lectura, no publica ni responde contenido. Se ejecuta
cada seis horas y puede ejecutarse manualmente. Las APIs y permisos de cada red
pueden exigir una aplicación registrada, OAuth, revisión o aprobación según el
tipo de cuenta.

## Operación y trazabilidad

- En una conexión usa **Probar conexión** para validar las credenciales antes de
  descubrir cuentas.
- Usa **Descubrir cuentas** para crear o actualizar las páginas, canales,
  perfiles u organizaciones disponibles para ese token.
- Usa **Sincronizar cuentas** para traer publicaciones, métricas e interacciones.
  La operación es idempotente: volver a sincronizar actualiza el registro
  existente y no crea copias.
- En **Conectores sociales → Historial de sincronizaciones** se puede revisar
  fecha, duración, estado, publicaciones, interacciones y detalle técnico de
  cada ejecución. El mismo historial está disponible desde cada conexión y
  cuenta.
- Las interacciones se pueden asignar a un responsable, marcar como respondidas
  y convertir en una actividad pendiente de Odoo.

El módulo registra clics, oportunidades atribuidas y ventas cuando el proveedor
o la importación entrega esos valores. Si una red no expone una métrica, se
guarda como cero y no se inventa información.

Referencias: [Instagram Graph API](https://developers.facebook.com/docs/instagram-api/),
[YouTube Data API](https://developers.google.com/youtube/v3),
[LinkedIn API](https://learn.microsoft.com/linkedin/),
[TikTok for Developers](https://developers.tiktok.com/).
