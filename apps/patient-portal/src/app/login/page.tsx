"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { hydrateSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";

const storageKey = "mediagent-patient-auth";
const isDevelopment = process.env.NODE_ENV === "development";

interface AuthResponse {
    tokens: {
        access_token: string;
    };
    user: {
        email: string;
        id: string;
        role: "patient" | "clinician";
    };
}

export default function LoginPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [email, setEmail] = useState(isDevelopment ? "sarah@example.com" : "");
    const [password, setPassword] = useState(isDevelopment ? "password123" : "");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setError("");

        try {
            const response = await api.post<AuthResponse>("/api/v1/auth/login", { email, password });
            if (response.user.role !== "patient") {
                throw new Error("This login belongs to a clinician account.");
            }

            const session = { token: response.tokens.access_token, user: response.user };
            window.localStorage.setItem(storageKey, JSON.stringify(session));
            dispatch(hydrateSession(session));
            router.replace("/today");
        } catch (submissionError) {
            setError((submissionError as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="app-shell min-h-dvh bg-gray-50 px-5 py-10">
            <div className="space-y-6">
                <div className="space-y-2 text-center">
                    <p className="text-sm font-medium text-blue-600">MediAgent</p>
                    <h1 className="text-3xl font-bold text-gray-900">Welcome back</h1>
                    <p className="text-sm text-gray-500">Sign in to your health companion.</p>
                </div>

                <Card padding="lg">
                    <form className="space-y-4" onSubmit={handleSubmit}>
                        <Input label="Email address" onChange={(event) => setEmail(event.target.value)} type="email" value={email} />
                        <Input label="Password" onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
                        {error ? <p className="text-sm text-red-600">{error}</p> : null}
                        <Button disabled={submitting} fullWidth type="submit">
                            {submitting ? "Signing in..." : "Sign in"}
                        </Button>
                    </form>
                </Card>

                <p className="text-center text-sm text-gray-500">
                    Need an account?{" "}
                    <Link className="font-medium text-blue-600" href="/signup">
                        Create one
                    </Link>
                </p>
            </div>
        </div>
    );
}
