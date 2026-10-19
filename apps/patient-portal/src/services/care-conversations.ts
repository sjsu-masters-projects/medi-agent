import { api } from "@/services/api";
import {
  createConversationService,
  getConversationCopy,
} from "../../../../packages/shared/src/utils/care-conversations";

export const careConversations = createConversationService(api);
export { getConversationCopy };
