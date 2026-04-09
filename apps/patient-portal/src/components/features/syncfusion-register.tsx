"use client";

import { useEffect } from "react";
import { registerLicense } from "@syncfusion/ej2-base";

let registered = false;

export function SyncfusionRegister() {
    useEffect(() => {
        if (registered) {
            return;
        }
        const key = process.env.NEXT_PUBLIC_SYNCFUSION_LICENSE_KEY;
        if (key) {
            registerLicense(key);
        }
        registered = true;
    }, []);

    return null;
}
