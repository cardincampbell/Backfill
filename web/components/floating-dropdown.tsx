"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";

type FloatingDropdownProps = {
  open: boolean;
  anchorRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  children: ReactNode;
  className: string;
  width?: number;
  minWidth?: number;
  maxWidth?: number;
  maxHeight?: number;
  sideOffset?: number;
  align?: "left" | "right";
  matchAnchorWidth?: boolean;
  zIndex?: number;
};

export function FloatingDropdown({
  open,
  anchorRef,
  onClose,
  children,
  className,
  width,
  minWidth,
  maxWidth,
  maxHeight = 280,
  sideOffset = 8,
  align = "left",
  matchAnchorWidth = false,
  zIndex = 9999,
}: FloatingDropdownProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) {
      setMenuStyle(null);
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        anchorRef.current?.contains(target) ||
        menuRef.current?.contains(target)
      ) {
        return;
      }
      onClose();
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [anchorRef, onClose, open]);

  useEffect(() => {
    if (!open || !anchorRef.current || typeof window === "undefined") {
      return;
    }

    function updatePosition() {
      const anchor = anchorRef.current;
      if (!anchor) {
        return;
      }

      const rect = anchor.getBoundingClientRect();
      const viewportPadding = 12;
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const requestedWidth = matchAnchorWidth
        ? rect.width
        : width ?? Math.max(rect.width, minWidth ?? 0);
      const boundedWidth = Math.min(
        requestedWidth,
        viewportWidth - viewportPadding * 2,
      );
      const spaceBelow = viewportHeight - rect.bottom - viewportPadding;
      const spaceAbove = rect.top - viewportPadding;
      const openUpward = spaceBelow < Math.min(maxHeight, 220) && spaceAbove > spaceBelow;
      const boundedMaxHeight = Math.max(
        120,
        Math.min(maxHeight, (openUpward ? spaceAbove : spaceBelow) - sideOffset),
      );
      const desiredLeft =
        align === "right" ? rect.right - boundedWidth : rect.left;
      const left = Math.min(
        Math.max(viewportPadding, desiredLeft),
        viewportWidth - boundedWidth - viewportPadding,
      );

      setMenuStyle({
        position: "fixed",
        left,
        right: "auto",
        width: boundedWidth,
        maxWidth,
        minWidth,
        maxHeight: boundedMaxHeight,
        zIndex,
        ...(openUpward
          ? { bottom: viewportHeight - rect.top + sideOffset }
          : { top: rect.bottom + sideOffset }),
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [
    align,
    anchorRef,
    matchAnchorWidth,
    maxHeight,
    maxWidth,
    minWidth,
    open,
    sideOffset,
    width,
    zIndex,
  ]);

  if (!open || !mounted || !menuStyle) {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      <motion.div
        ref={menuRef}
        initial={{ opacity: 0, y: 4, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 4, scale: 0.98 }}
        transition={{ duration: 0.15 }}
        className={className}
        style={menuStyle}
      >
        {children}
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}
