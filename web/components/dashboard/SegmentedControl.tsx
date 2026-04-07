"use client";

import type { LucideIcon } from "lucide-react";

type SegmentedControlItem<T extends string> = {
  value: T;
  label: string;
  icon?: LucideIcon;
  activeClassName?: string;
  inactiveClassName?: string;
};

type SegmentedControlProps<T extends string> = {
  items: readonly SegmentedControlItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  radiusClassName?: string;
  itemRadiusClassName?: string;
  itemClassName?: string;
  activeItemClassName?: string;
  inactiveItemClassName?: string;
  activeWeight?: number;
  inactiveWeight?: number;
  iconSize?: number;
};

function joinClasses(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export default function SegmentedControl<T extends string>({
  items,
  value,
  onChange,
  className,
  radiusClassName = "backfill-ui-radius",
  itemRadiusClassName = "backfill-ui-radius",
  itemClassName,
  activeItemClassName,
  inactiveItemClassName,
  activeWeight = 520,
  inactiveWeight = 440,
  iconSize = 14,
}: SegmentedControlProps<T>) {
  return (
    <div
      className={joinClasses(
        "inline-flex items-center gap-0.5 p-1",
        radiusClassName,
        className,
      )}
    >
      {items.map((item) => {
        const active = item.value === value;
        const Icon = item.icon;

        return (
          <button
            key={item.value}
            onClick={() => onChange(item.value)}
            className={joinClasses(
              "flex items-center justify-center gap-1.5 px-4 py-2.5 text-[13px] transition-all duration-200",
              itemRadiusClassName,
              itemClassName,
              active
                ? item.activeClassName ?? activeItemClassName
                : item.inactiveClassName ?? inactiveItemClassName,
            )}
            style={{ fontWeight: active ? activeWeight : inactiveWeight }}
            type="button"
          >
            {Icon ? <Icon size={iconSize} /> : null}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
