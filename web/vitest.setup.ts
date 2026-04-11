import "@testing-library/jest-dom/vitest";
import React from "react";
import { vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
    href: string;
    children: React.ReactNode;
  }) => React.createElement("a", { href, ...props }, children),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
  }),
  usePathname: () => "/dashboard",
}));

vi.mock("motion/react", async () => {
  const ReactModule = await import("react");
  const createMotionComponent = (tag: string) =>
    ReactModule.forwardRef<
      HTMLElement,
      { children?: React.ReactNode } & Record<string, unknown>
    >(
      ({ children, ...props }, ref) =>
        ReactModule.createElement(
          tag,
          { ref, ...(props as Record<string, unknown>) },
          (children ?? null) as React.ReactNode,
        ),
    );

  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) =>
      ReactModule.createElement(ReactModule.Fragment, null, children),
    motion: {
      div: createMotionComponent("div"),
      button: createMotionComponent("button"),
    },
  };
});

if (typeof HTMLElement !== "undefined") {
  HTMLElement.prototype.scrollIntoView = vi.fn();
}
