"use client";

import NextLink, { type LinkProps as NextLinkProps } from "next/link";
import { useRouter } from "next/navigation";
import type { ComponentProps } from "react";

type LinkProps = Omit<ComponentProps<typeof NextLink>, "href"> &
  Omit<NextLinkProps, "href"> & {
    to: NextLinkProps["href"];
  };

export function Link({ to, ...props }: LinkProps) {
  return <NextLink href={to} {...props} />;
}

export function useNavigate() {
  const router = useRouter();

  return (href: string) => {
    router.push(href);
  };
}
