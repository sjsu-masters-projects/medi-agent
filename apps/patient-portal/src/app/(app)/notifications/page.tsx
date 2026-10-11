"use client";

import { NotificationCentre } from "@/components/features/notification-centre";
import { useNotifications } from "@/contexts/notifications-context";
import { getNotificationsCopy } from "@/content/notifications-copy";
import { PageHeader } from "@/components/layouts/page-header";

export default function NotificationsPage() {
  const { locale } = useNotifications();
  // The header carries its own padding, like every other patient page; only the list is inset.
  return <div className="patient-page space-y-3 pb-6" lang={locale}>
    <PageHeader backButton title={getNotificationsCopy(locale).title} />
    <div className="px-4"><NotificationCentre /></div>
  </div>;
}
