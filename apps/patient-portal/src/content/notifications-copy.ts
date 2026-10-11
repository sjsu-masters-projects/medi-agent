export function getNotificationsCopy(locale: string) {
  return locale === "es-MX" ? {
    title: "Notificaciones", all: "Todas", unread: "Sin leer", read: "Marcar como leída",
    readAll: "Marcar las mostradas como leídas", full: "Ver todas las notificaciones", close: "Cerrar notificaciones",
    refresh: "Actualizar", loading: "Cargando notificaciones…", empty: "No hay notificaciones.",
    emptyUnread: "No hay notificaciones sin leer.", unavailable: "El conteo no está disponible.",
    loadError: "No se pudieron actualizar las notificaciones. Intenta de nuevo.",
    writeError: "No se pudo confirmar la lectura. Actualiza antes de intentar de nuevo.",
    more: "Cargar más", notice: "Marcar como leída no significa revisar ni aprobar la atención.",
    count: (count: number) => `${count} sin leer`,
  } : {
    title: "Notifications", all: "All", unread: "Unread", read: "Mark as read",
    readAll: "Mark displayed as read", full: "View all notifications", close: "Close notifications",
    refresh: "Refresh", loading: "Loading notifications…", empty: "No notifications yet.",
    emptyUnread: "No unread notifications.", unavailable: "Count unavailable.",
    loadError: "Notifications could not be refreshed. Try again.",
    writeError: "Read could not be confirmed. Refresh before trying again.",
    more: "Load more", notice: "Marking as read does not review or approve care.",
    count: (count: number) => `${count} unread`,
  };
}
