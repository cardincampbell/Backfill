"use client";

import {
  useCallback,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";

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
  const pathname = usePathname();
  const [workspace, setWorkspace] = useState<Workspace | null>(initialWorkspace);
  const [workspaceReady, setWorkspaceReady] = useState(Boolean(initialWorkspace));
  const refreshRequestRef = useRef(0);
  const hasHandledInitialPathRef = useRef(false);

  const refreshWorkspace = useCallback(async () => {
    const requestId = ++refreshRequestRef.current;
    try {
      const nextWorkspace = await getWorkspace();
      if (requestId !== refreshRequestRef.current) {
        return;
      }
      setWorkspace((current) => nextWorkspace ?? current);
    } finally {
      if (requestId === refreshRequestRef.current) {
        setWorkspaceReady(true);
      }
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

  useEffect(() => {
    if (!pathname) {
      return;
    }
    if (!hasHandledInitialPathRef.current) {
      hasHandledInitialPathRef.current = true;
      if (initialWorkspace) {
        return;
      }
    }
    void refreshWorkspace();
  }, [initialWorkspace, pathname, refreshWorkspace]);

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

export function useAppWorkspaceRefresh() {
  return (
    useContext(AppWorkspaceContext)?.refreshWorkspace ??
    (async () => {
      return;
    })
  );
}

export function useAppWorkspaceLocations(): WorkspaceLocation[] {
  return useAppWorkspace()?.locations ?? [];
}
