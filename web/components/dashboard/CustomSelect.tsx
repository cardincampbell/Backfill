"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, Check } from "lucide-react";

export type CustomSelectOption = {
  value: string;
  label: string;
};

export type CustomSelectProps = {
  options: CustomSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

export default function CustomSelect({
  options,
  value,
  onChange,
  placeholder,
}: CustomSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const selected = options.find((option) => option.value === value);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg border text-[13px] text-left transition-all duration-200 bg-white ${
          open
            ? "border-[#635BFF]/40 shadow-[0_0_0_3px_rgba(99,91,255,0.08)]"
            : "border-[#E5E7EB] hover:border-[#D1D5DB]"
        }`}
        style={{ fontWeight: 440 }}
      >
        <span className={selected ? "text-[#0A2540]" : "text-[#8898AA]/60"}>
          {selected?.label || placeholder || "Select..."}
        </span>
        <ChevronDown
          size={14}
          className={`text-[#8898AA] transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: 4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 left-0 right-0 mt-1.5 bg-white border border-[#E5E7EB] rounded-xl shadow-[0_8px_30px_rgba(0,0,0,0.08),0_0_0_1px_rgba(0,0,0,0.02)] overflow-hidden py-1"
          >
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 text-[13px] text-left transition-all duration-150 ${
                  option.value === value
                    ? "bg-[#635BFF]/[0.06] text-[#635BFF]"
                    : "text-[#3E4C59] hover:bg-[#F7F8FA]"
                }`}
                style={{ fontWeight: option.value === value ? 520 : 440 }}
              >
                {option.label}
                {option.value === value ? (
                  <Check size={13} className="text-[#635BFF]" />
                ) : null}
              </button>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
