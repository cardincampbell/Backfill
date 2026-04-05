"use client";

import {
  Children,
  isValidElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ChangeEventHandler,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";

type SelectLikeEvent = {
  target: {
    value: string;
  };
};

type SelectOption = {
  value: string;
  label: ReactNode;
  disabled?: boolean;
};

type BrandedSelectProps = {
  value: string;
  onChange?: ChangeEventHandler<HTMLSelectElement> | ((event: SelectLikeEvent) => void);
  dark?: boolean;
  className?: string;
  children?: ReactNode;
  options?: SelectOption[];
};

function extractOptions(children: ReactNode): SelectOption[] {
  return Children.toArray(children).flatMap((child) => {
    if (!isValidElement(child) || child.type !== "option") {
      return [];
    }

    const optionElement = child as ReactElement<{
      value?: string;
      disabled?: boolean;
      children?: ReactNode;
    }>;

    const value =
      typeof optionElement.props.value === "string"
        ? optionElement.props.value
        : String(optionElement.props.value ?? "");

    return [
      {
        value,
        label: optionElement.props.children,
        disabled: Boolean(optionElement.props.disabled),
      },
    ];
  });
}

export function BrandedSelect({
  value,
  onChange,
  dark = false,
  className,
  children,
  options,
}: BrandedSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const controlRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);
  const [mounted, setMounted] = useState(false);
  const resolvedOptions = useMemo(
    () => options ?? extractOptions(children),
    [children, options],
  );

  const selectedOption =
    resolvedOptions.find((option) => option.value === value) ??
    resolvedOptions[0] ??
    null;

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

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
        Math.min(
          320,
          (openUpward ? spaceAbove : spaceBelow) - spacing,
        ),
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

  const controlClass = dark
    ? "border-white/[0.08] bg-[linear-gradient(180deg,rgba(99,91,255,0.18),rgba(15,46,76,0.98))] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_18px_36px_rgba(0,0,0,0.24)]"
    : "border-[#D7DEEA] bg-[linear-gradient(180deg,rgba(99,91,255,0.10),rgba(255,255,255,0.98))] text-[#0A2540] shadow-[inset_0_1px_0_rgba(255,255,255,0.6),0_14px_30px_rgba(10,37,64,0.08)]";
  const menuClass = dark
    ? "border-white/[0.08] bg-[#0F2E4C]/[0.98] text-white shadow-[0_28px_64px_rgba(0,0,0,0.36)]"
    : "border-[#E5E7EB] bg-white text-[#0A2540] shadow-[0_24px_56px_rgba(10,37,64,0.12)]";
  const optionBaseClass = dark
    ? "text-[#C1CED8] hover:bg-white/[0.06] hover:text-white"
    : "text-[#425466] hover:bg-[#F7F8FA] hover:text-[#0A2540]";
  const selectedClass = dark
    ? "bg-[#635BFF]/[0.18] text-white"
    : "bg-[#635BFF]/[0.08] text-[#635BFF]";

  function handleSelect(nextValue: string) {
    setOpen(false);
    onChange?.({ target: { value: nextValue } } as never);
  }

  const menu = open && mounted && menuStyle
    ? createPortal(
        <AnimatePresence>
          <motion.div
            ref={menuRef}
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className={`overflow-hidden backfill-ui-radius border p-1.5 ${menuClass}`}
            style={menuStyle}
          >
            <div className="overflow-y-auto" style={{ maxHeight: menuStyle.maxHeight }}>
              {resolvedOptions.map((option) => {
                const selected = option.value === value;
                return (
                  <button
                    key={`${option.value}-${String(option.label)}`}
                    type="button"
                    disabled={option.disabled}
                    onClick={() => handleSelect(option.value)}
                    className={`flex w-full items-center backfill-ui-radius px-3 py-2.5 text-left text-[12px] transition-colors ${selected ? selectedClass : optionBaseClass} ${option.disabled ? "cursor-not-allowed opacity-45" : ""}`}
                    style={{ fontWeight: selected ? 540 : 430 }}
                  >
                    <span className="min-w-0 truncate">{option.label}</span>
                  </button>
                );
              })}
            </div>
          </motion.div>
        </AnimatePresence>,
        document.body,
      )
    : null;

  return (
    <div ref={rootRef} className={`relative ${className ?? ""}`}>
      <button
        ref={controlRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((current) => !current)}
        className={`flex min-h-[44px] w-full items-center justify-between gap-3 backfill-ui-radius border px-3.5 py-2.5 text-left text-[13px] transition-all focus:outline-none focus:border-[#635BFF]/60 focus:shadow-[0_0_0_4px_rgba(99,91,255,0.12)] ${controlClass}`}
        style={{ fontWeight: 440 }}
      >
        <span className="min-w-0 truncate">
          {selectedOption?.label ?? <span className="text-[#8898AA]">Select</span>}
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 transition-transform ${dark ? "text-[#A7B7FF]" : "text-[#635BFF]"} ${open ? "rotate-180" : ""}`}
        />
      </button>
      {menu}
    </div>
  );
}
