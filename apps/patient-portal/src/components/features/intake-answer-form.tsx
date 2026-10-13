"use client";

import { useEffect, useRef, useState } from "react";
import { getSymptomIntakeCopy } from "@/content/symptom-intake-copy";
import type { IntakeAnswer, IntakeQuestion, Locale } from "@/types";

const input = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500";
const button = "min-h-11 rounded-lg border border-gray-300 px-3 py-2 text-sm disabled:opacity-50";
export function IntakeAnswerForm({ question, locale, answer, disabled, save }: {
    question: IntakeQuestion; locale: Locale; answer?: IntakeAnswer; disabled: boolean;
    save: (state: "answered" | "unknown" | "declined", value: IntakeAnswer["value"], wording: string) => void;
}) {
    const copy = getSymptomIntakeCopy(locale);
    const form = useRef<HTMLFormElement>(null);
    useEffect(() => {
        if (!disabled && (document.activeElement === document.body || form.current?.contains(document.activeElement))) {
            form.current?.querySelector<HTMLElement>("textarea, select, input")?.focus();
        }
    }, [disabled, question.id]);
    const [value, setValue] = useState(typeof answer?.value === "string" || typeof answer?.value === "number" ? String(answer.value) : "");
    const [boolean, setBoolean] = useState(answer?.value === true ? "true" : answer?.value === false ? "false" : "");
    const [product, setProduct] = useState<Record<string, string>>(answer?.value && typeof answer.value === "object"
        ? Object.fromEntries(Object.entries(answer.value).map(([k, v]) => [k, String(v)])) : {});
    const fields = { name: copy.name, strength: copy.strength, dose: copy.dose, route: copy.route, indication: copy.indication,
        start: copy.startDate, stop: copy.stop, change: copy.change };
    const id = `intake-answer-${question.id}`;
    return <form ref={form} className="space-y-3" onSubmit={(event) => {
        event.preventDefault();
        const accepted: IntakeAnswer["value"] = question.answer_type === "rating" ? Number(value)
            : question.answer_type === "boolean" ? boolean === "true"
                : question.answer_type === "product" ? { ...Object.fromEntries(Object.entries(product).filter(([,v]) => v.trim())), concern: product.concern === "true" } : value;
        save("answered", accepted, typeof accepted === "string" ? accepted : value);
    }}>
        <label id={`${id}-label`} htmlFor={id} className="block font-medium">{question.wording[locale]}</label>
        <fieldset aria-label={copy.value} disabled={disabled} className="space-y-3">
            {question.answer_type === "text" && <textarea id={id} className={input} value={value} maxLength={1000} required onChange={(e) => setValue(e.target.value)} />}
            {question.answer_type === "rating" && <select id={id} className={input} value={value} required onChange={(e) => setValue(e.target.value)}>
                <option value="">{copy.value}</option>{Array.from({ length: 10 }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}</select>}
            {question.answer_type === "boolean" && <select id={id} className={input} value={boolean} required onChange={(e) => setBoolean(e.target.value)}>
                <option value="">{copy.value}</option><option value="true">{copy.yes}</option><option value="false">{copy.no}</option></select>}
            {question.answer_type === "product" && <><select id={id} className={input} required value={product.concern ?? ""}
                onChange={(e) => setProduct(e.target.value === "false" ? { concern: "false" } : { ...product, concern: e.target.value })}>
                <option value="">{copy.productConcern}</option><option value="true">{copy.yes}</option><option value="false">{copy.no}</option></select>
                {product.concern === "true" && Object.entries(fields).map(([key, label]) => <label key={key} className="block text-sm">{label}
                    <input className={input} required={key === "name"} maxLength={300} value={product[key] ?? ""}
                        onChange={(e) => setProduct({ ...product, [key]: e.target.value })} /></label>)}</>}
            <div className="flex flex-wrap gap-2"><button className={button} type="submit">{copy.save}</button>
                <button className={button} type="button" onClick={() => save("unknown", null, "")}>{copy.unknown}</button>
                <button className={button} type="button" onClick={() => save("declined", null, "")}>{copy.declined}</button></div>
        </fieldset>
    </form>;
}
