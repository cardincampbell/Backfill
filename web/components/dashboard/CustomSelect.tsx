"use client";

import { useState, useRef, useEffect, type CSSProperties } from "react";
import { createPortal } from "react-dom";
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
  const controlRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        ref.current &&
        !ref.current.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, []);

  useEffect(() => {
    if (!open || !controlRef.current || typeof window === "undefined") {
      return;
    }

    function updatePosition() {
      if (!controlRef.current) {
        return;
      }

      const rect = controlRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const viewportWidth = window.innerWidth;
      const spacing = 8;
      const viewportPadding = 12;
      const spaceBelow = viewportHeight - rect.bottom - viewportPadding;
      const spaceAbove = rect.top - viewportPadding;
      const openUpward = spaceBelow < 200 && spaceAbove > spaceBelow;
      const maxHeight = Math.max(
        120,
        Math.min(320, (openUpward ? spaceAbove : spaceBelow) - spacing),
      );
      const width = Math.min(rect.width, viewportWidth - viewportPadding * 2);
      const left = Math.min(
        Math.max(viewportPadding, rect.left),
        viewportWidth - width - viewportPadding,
      );

      setMenuStyle({
        position: "fixed",
        left,
        width,
        maxHeight,
        zIndex: 9999,
        ...(openUpward
          ? { bottom: viewportHeight - rect.top + spacing }
          : { top: rect.bottom + spacing }),
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  const selected = options.find((option) => option.value === value);

  const menu =
    open && mounted && menuStyle
      ? createPortal(
          <AnimatePresence>
            <motion.div
              ref={menuRef}
              initial={{ opacity: 0, y: 4, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.98 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white py-1 shadow-[0_8px_30px_rgba(0,0,0,0.08),0_0_0_1px_rgba(0,0,0,0.02)]"
              style={menuStyle}
            >
              <div className="overflow-y-auto" style={{ maxHeight: menuStyle.maxHeight }}>
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
              </div>
            </motion.div>
          </AnimatePresence>,
          document.body,
        )
      : null;

  return (
    <div ref={ref} className={`relative ${open ? "z-20" : ""}`}>
      <button
        ref={controlRef}
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
      {menu}
    </div>
  );
}
