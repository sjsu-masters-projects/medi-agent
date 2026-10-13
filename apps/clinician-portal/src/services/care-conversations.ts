import { api } from "@/services/api";
import { createConversationService } from "../../../../packages/shared/src/utils/care-conversations";

export const careConversations = createConversationService(api);
