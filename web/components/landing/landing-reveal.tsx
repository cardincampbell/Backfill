"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";

type LandingRevealProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
  duration?: number;
  distance?: number;
  axis?: "x" | "y";
  opacityOnly?: boolean;
  as?: "div" | "blockquote";
};

const MOTION_TAGS = {
  div: motion.div,
  blockquote: motion.blockquote,
} as const;

export function LandingReveal({
  children,
  className,
  delay = 0,
  duration = 0.6,
  distance = 20,
  axis = "y",
  opacityOnly = false,
  as = "div",
}: LandingRevealProps) {
  const MotionTag = MOTION_TAGS[as];
  const initial = opacityOnly
    ? { opacity: 0 }
    : axis === "x"
      ? { opacity: 0, x: -distance }
      : { opacity: 0, y: distance };
  const animate = opacityOnly
    ? { opacity: 1 }
    : axis === "x"
      ? { opacity: 1, x: 0 }
      : { opacity: 1, y: 0 };

  return (
    <MotionTag
      initial={initial}
      whileInView={animate}
      viewport={{ once: true }}
      transition={{ duration, delay }}
      className={className}
    >
      {children}
    </MotionTag>
  );
}
