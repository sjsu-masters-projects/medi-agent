import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { dispatch, replace } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
}));

vi.mock("@/services/api", () => ({
    api: { post: vi.fn() },
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession: vi.fn(),
}));

import SignupPage from "@/app/(auth)/signup/page";

describe("Patient signup page", () => {
    beforeEach(() => {
        dispatch.mockReset();
        replace.mockReset();
    });

    it("lets patients inspect and hide both password fields", () => {
        render(<SignupPage />);

        const password = screen.getByLabelText(/^password$/i);
        const confirmPassword = screen.getByLabelText(/^confirm password$/i);

        expect(password).toHaveAttribute("type", "password");
        expect(confirmPassword).toHaveAttribute("type", "password");

        fireEvent.click(screen.getByRole("button", { name: /^show password$/i }));
        fireEvent.click(screen.getByRole("button", { name: /^show confirm password$/i }));

        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");
        expect(screen.getByLabelText(/^confirm password$/i)).toHaveAttribute("type", "text");

        fireEvent.click(screen.getByRole("button", { name: /^hide password$/i }));
        fireEvent.click(screen.getByRole("button", { name: /^hide confirm password$/i }));

        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
        expect(screen.getByLabelText(/^confirm password$/i)).toHaveAttribute("type", "password");
    });
});
