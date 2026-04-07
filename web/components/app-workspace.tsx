"use client";

import {
  useCallback,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  getWorkspace,
  type Workspace,
  type WorkspaceLocation,
} from "@/lib/api/workspace";

type AppWorkspaceContextValue = {
  workspace: Workspace | null;
  workspaceReady: boolean;
  refreshWorkspace: () => Promise<void>;
};

const AppWorkspaceContext = createContext<AppWorkspaceContextValue | null>(null);

export function AppWorkspaceProvider({
  children,
  initialWorkspace,
}: {
  children: ReactNode;
  initialWorkspace: Workspace | null;
}) {
  const [workspace, setWorkspace] = useState<Workspace | null>(initialWorkspace);
  const [workspaceReady, setWorkspaceReady] = useState(Boolean(initialWorkspace));

  const refreshWorkspace = useCallback(async () => {
    try {
      const nextWorkspace = await getWorkspace();
      setWorkspace(nextWorkspace);
    } finally {
      setWorkspaceReady(true);
    }
  }, []);

  useEffect(() => {
    if (initialWorkspace) {
      setWorkspace(initialWorkspace);
      setWorkspaceReady(true);
      return;
    }
    void refreshWorkspace();
  }, [initialWorkspace, refreshWorkspace]);

  const value = useMemo<AppWorkspaceContextValue>(
    () => ({
      workspace,
      workspaceReady,
      refreshWorkspace,
    }),
    [refreshWorkspace, workspace, workspaceReady],
  );

  return (
    <AppWorkspaceContext.Provider value={value}>
      {children}
    </AppWorkspaceContext.Provider>
  );
}

export function useAppWorkspace() {
  return useContext(AppWorkspaceContext)?.workspace ?? null;
}

export function useAppWorkspaceReady() {
  return useContext(AppWorkspaceContext)?.workspaceReady ?? false;
}

export function useAppWorkspaceLocations(): WorkspaceLocation[] {
  return useAppWorkspace()?.locations ?? [];
}
