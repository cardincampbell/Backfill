import Settings from "@/components/dashboard/Settings";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <Settings embeddedInShell />
      {children}
    </>
  );
}
