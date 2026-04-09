import { EmptyState } from "@/components/ui";
import { HiOutlineExclamationTriangle } from "react-icons/hi2";

export default function MedWatchPage() {
    return (
        <EmptyState
            description="Pending FDA drafts will appear here for review."
            icon={<HiOutlineExclamationTriangle />}
            title="No MedWatch drafts"
        />
    );
}
