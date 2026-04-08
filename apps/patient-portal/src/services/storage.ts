import { createClient, type SupabaseClient } from "@supabase/supabase-js";

interface UploadDocumentParams {
    file: File;
    patientId: string;
    token: string;
}

function sanitizeFileName(fileName: string) {
    return fileName
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "-")
        .replace(/[^a-z0-9._-]/g, "");
}

function createStorageClient(token: string): SupabaseClient {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (!supabaseUrl || !supabaseAnonKey) {
        throw new Error("Supabase Storage is not configured for the patient portal.");
    }

    return createClient(supabaseUrl, supabaseAnonKey, {
        accessToken: async () => token,
        auth: {
            autoRefreshToken: false,
            detectSessionInUrl: false,
            persistSession: false,
        },
    });
}

export async function uploadDocumentToStorage({
    file,
    patientId,
    token,
}: UploadDocumentParams): Promise<string> {
    const supabase = createStorageClient(token);
    const safeName = sanitizeFileName(file.name) || `document-${Date.now()}`;
    const filePath = `${patientId}/${Date.now()}-${safeName}`;

    const { data, error } = await supabase.storage.from("documents").upload(filePath, file, {
        cacheControl: "3600",
        contentType: file.type || "application/octet-stream",
        upsert: false,
    });

    if (error) {
        throw new Error(error.message);
    }

    return data.path;
}
