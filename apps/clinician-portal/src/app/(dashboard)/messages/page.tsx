import { EmptyState } from "@/components/ui";
import { HiOutlineChatBubbleLeftRight } from "react-icons/hi2";

export default function MessagesPage() {
    return (
        <EmptyState
            description="Clinician and patient communication threads will appear here."
            icon={<HiOutlineChatBubbleLeftRight />}
            title="No messages yet"
        />
    );
}
