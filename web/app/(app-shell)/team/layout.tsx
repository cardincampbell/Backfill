import Team from "@/components/dashboard/Team";

export default function TeamLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <Team embeddedInShell />
      {children}
    </>
  );
}
