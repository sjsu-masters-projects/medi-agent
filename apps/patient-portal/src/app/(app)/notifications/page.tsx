"use client";

import { NotificationCentre } from "@/components/features/notification-centre";
import { useNotifications } from "@/contexts/notifications-context";
import { getNotificationsCopy } from "@/content/notifications-copy";
import { PageHeader } from "@/components/layouts/page-header";

export default function NotificationsPage() {
  const { locale } = useNotifications();
  return <div className="patient-page space-y-5 px-4 pb-6" lang={locale}>
    <PageHeader title={getNotificationsCopy(locale).title} />
    <NotificationCentre />
  </div>;
}
