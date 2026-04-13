"use client";

import { useState, useRef, useEffect, useMemo, type ReactNode } from 'react';
import { Link, useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import {
  useResolvedAppAppearance,
  useSessionUserDisplay,
} from '@/components/app-session-gate';
import {
  useAppWorkspace,
  useAppWorkspaceReady,
} from '@/components/app-workspace';
import { useLocationEntryRouting } from '@/components/location-entry-provider';
import { signOutClientSession } from '@/lib/auth/client-signout';
import {
  buildDashboardLocationBasePathFromAny,
  buildSchedulerBasePathFromAny,
  findLocationByDashboardSlugsFromAny,
} from '@/lib/dashboard-paths';
import {
  persistAppShellSidebarTabPreference,
  type AppShellSidebarTab,
} from '@/lib/app-shell-prefs';
import { buildSettingsPath } from '@/lib/settings-routing';
import { preloadSchedulerBootstrap } from '@/lib/scheduler-bootstrap';
import { resolvePreferredWorkspaceBusiness } from '@/lib/workspace-business';
import { usePathname, useRouter } from 'next/navigation';
import {
  Users,
  Activity,
  Calendar,
  Bell,
  Search,
  Settings,
  CheckCircle2,
  AlertCircle,
  LayoutGrid,
  Navigation,
  HelpCircle,
  LifeBuoy,
  Sparkles,
  Menu,
  X,
  Plus,
  LogOut,
  ChevronDown,
} from 'lucide-react';
import {
  findSourceDashboardLocationBySlug,
  sourceDashboardNotifications,
} from './mock-data';
import AddLocationModal from './AddLocationModal';
import DashboardCopilotSidebar from './DashboardCopilotSidebar';

const navItems = [
  { label: 'Overview', icon: LayoutGrid, path: '/dashboard' },
  { label: 'Team', icon: Users, path: '/team' },
  { label: 'Activity', icon: Activity, path: '/activity' },
  { label: 'Schedule', icon: Calendar, path: '/schedule' },
];

interface DashboardShellProps {
  activeNav: string;
  children: ReactNode;
  initialSidebarTab?: AppShellSidebarTab;
}

type DashboardShellLocationShortcut = {
  id: string;
  businessSlug?: string | null;
  slug: string;
  name: string;
  logo: string;
  openShifts?: number | null;
  entryPath: string;
  setupPath: string;
  schedulerPath: string;
  isWorkspaceBacked: boolean;
};

export default function DashboardShell({
  activeNav,
  children,
  initialSidebarTab = 'nav',
}: DashboardShellProps) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showAddLocation, setShowAddLocation] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<AppShellSidebarTab>(initialSidebarTab);
  const [copilotActivationCount, setCopilotActivationCount] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const navigate = useNavigate();
  const router = useRouter();
  const pathname = usePathname();
  const workspace = useAppWorkspace();
  const workspaceLocationsLoaded = useAppWorkspaceReady();
  const workspaceLocations = workspace?.locations ?? [];
  const { getLocationEntryHref } = useLocationEntryRouting();
  const resolvedAppearance = useResolvedAppAppearance();
  const isDark = resolvedAppearance === 'dark';
  const { fullName, email, phone, initials } = useSessionUserDisplay();
  const userMenuRef = useRef<HTMLDivElement | null>(null);

  const shellBgClass = isDark ? 'bg-[#071B2F]' : 'bg-[#F7F8FA]';
  const panelBgClass = isDark ? 'bg-[#0F2E4C]' : 'bg-white';
  const panelBorderClass = isDark ? 'border-white/[0.06]' : 'border-[#E5E7EB]';
  const sectionBorderClass = isDark ? 'border-white/[0.06]' : 'border-[#F0F0F5]';
  const textPrimaryClass = isDark ? 'text-white' : 'text-[#0A2540]';
  const textSecondaryClass = isDark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]';
  const mutedTextClass = 'text-[#8898AA]';
  const subtleSurfaceClass = isDark ? 'bg-white/[0.03]' : 'bg-[#F0F0F5]';
  const hoverSurfaceClass = isDark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]';
  const searchFieldClass = isDark
    ? 'bg-white/[0.04] border-white/[0.06] text-white placeholder-[#8898AA]/50'
    : 'bg-[#F7F8FA] border-[#E5E7EB] text-[#0A2540] placeholder-[#8898AA]/60';

  useEffect(() => {
    persistAppShellSidebarTabPreference(sidebarTab);
  }, [sidebarTab]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(event.target as Node)
      ) {
        setShowUserMenu(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, []);

  const locationShortcuts = useMemo<DashboardShellLocationShortcut[]>(() => {
    if (workspaceLocationsLoaded && workspaceLocations.length > 0) {
      return workspaceLocations.map((location) => {
        const referenceLocation = findSourceDashboardLocationBySlug(
          location.location_slug,
        );
        const path = buildDashboardLocationBasePathFromAny({
          business_slug: location.business_slug,
          location_slug: location.location_slug,
          business_name: location.business_display_name,
          location_name: location.location_name,
          location_display_name: location.location_display_name,
          location_id: location.location_id,
        });
        const schedulerPath = buildSchedulerBasePathFromAny({
          business_slug: location.business_slug,
          location_slug: location.location_slug,
          business_name: location.business_display_name,
          location_name: location.location_name,
          location_display_name: location.location_display_name,
          location_id: location.location_id,
        });
        return {
          id: location.location_id,
          businessSlug: location.business_slug,
          slug: location.location_slug,
          name: location.location_display_name ?? location.location_name,
          logo: referenceLocation?.logo ?? '📍',
          openShifts: referenceLocation?.openShifts ?? null,
          entryPath: getLocationEntryHref(location),
          setupPath: path,
          schedulerPath,
          isWorkspaceBacked: true,
        };
      });
    }

    return [];
  }, [getLocationEntryHref, workspaceLocations, workspaceLocationsLoaded]);

  const preferredBusiness = useMemo(
    () => resolvePreferredWorkspaceBusiness(workspace, pathname),
    [pathname, workspace],
  );
  const activeWorkspaceLocation = useMemo(() => {
    if (!pathname) {
      return null;
    }
    const parts = pathname.split('/').filter(Boolean);
    if (parts.length < 3) {
      return null;
    }
    if (parts[0] !== 'location' && parts[0] !== 'scheduler') {
      return null;
    }
    return findLocationByDashboardSlugsFromAny(
      workspaceLocations,
      parts[1] ?? '',
      parts[2] ?? '',
    );
  }, [pathname, workspaceLocations]);

  const preferredSchedulerLocation = useMemo(
    () => activeWorkspaceLocation ?? workspaceLocations[0] ?? null,
    [activeWorkspaceLocation, workspaceLocations],
  );

  useEffect(() => {
    if (!preferredSchedulerLocation) {
      return;
    }
    const schedulerTarget = buildSchedulerBasePathFromAny(preferredSchedulerLocation);
    router.prefetch(schedulerTarget);
    void preloadSchedulerBootstrap(
      preferredSchedulerLocation.business_id,
      preferredSchedulerLocation.location_id,
    );
  }, [preferredSchedulerLocation, router]);

  const handleNav = (path: string) => {
    if (path === '/schedule') {
      const schedulerTargetLocation = activeWorkspaceLocation ?? workspaceLocations[0] ?? null;
      if (schedulerTargetLocation) {
        void preloadSchedulerBootstrap(
          schedulerTargetLocation.business_id,
          schedulerTargetLocation.location_id,
        );
      }
      const schedulerTarget =
        schedulerTargetLocation
          ? buildSchedulerBasePathFromAny(schedulerTargetLocation)
          : locationShortcuts[0]?.schedulerPath ?? '/schedule';
      router.prefetch(schedulerTarget);
      navigate(schedulerTarget);
    } else {
      navigate(path);
    }
    setSidebarOpen(false);
    setShowNotifications(false);
    setShowUserMenu(false);
  };

  return (
    <div
      className={`min-h-screen flex ${shellBgClass}`}
      style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
    >
      <AnimatePresence>
        {sidebarOpen ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        ) : null}
      </AnimatePresence>

      <aside
        className={`fixed top-0 left-0 h-full z-50 w-full lg:w-[300px] flex flex-col border-r ${panelBorderClass} ${panelBgClass} transition-transform duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className={`flex items-center justify-between h-16 px-5 border-b ${sectionBorderClass}`}>
          <Link to="/" className="flex items-center gap-2.5">
            <span className={`text-[18px] tracking-[-0.02em] ${textPrimaryClass}`} style={{ fontWeight: 620 }}>
              Backfill
            </span>
          </Link>
          <button
            onClick={() => setSidebarOpen(false)}
            className={`p-1.5 rounded-lg transition-colors lg:hidden ${hoverSurfaceClass}`}
            type="button"
          >
            <X size={18} className={mutedTextClass} />
          </button>
        </div>

        <div className="px-3 pt-3 pb-1">
          <div className={`flex items-center rounded-lg p-0.5 ${subtleSurfaceClass}`}>
            <button
              onClick={() => {
                setSidebarTab('copilot');
                setCopilotActivationCount((current) => current + 1);
              }}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2.5 text-[13px] transition-all duration-200 ${
                sidebarTab === 'copilot'
                  ? 'bg-[#635BFF]/10 text-[#635BFF] shadow-sm'
                  : `${mutedTextClass} ${isDark ? 'hover:text-white' : 'hover:text-[#0A2540]'}`
              }`}
              style={{ fontWeight: sidebarTab === 'copilot' ? 520 : 440 }}
              type="button"
            >
              <Sparkles size={14} />
              Copilot
            </button>
            <button
              onClick={() => setSidebarTab('nav')}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2.5 text-[13px] transition-all duration-200 ${
                sidebarTab === 'nav'
                  ? `${panelBgClass} ${textPrimaryClass} shadow-sm`
                  : `${mutedTextClass} ${isDark ? 'hover:text-white' : 'hover:text-[#0A2540]'}`
              }`}
              style={{ fontWeight: sidebarTab === 'nav' ? 520 : 440 }}
              type="button"
            >
              <Navigation size={14} />
              Navigate
            </button>
          </div>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
          <AnimatePresence mode="wait">
            {sidebarTab === 'nav' ? (
              <motion.div
                key="nav"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.2 }}
                className="flex-1 flex flex-col"
              >
                <nav className="flex-1 py-3 px-3 space-y-1 overflow-y-auto">
                  {navItems.map((item) => {
                    const isActive =
                      item.label === 'Schedule'
                        ? Boolean(pathname && (pathname === '/schedule' || pathname.startsWith('/scheduler/')))
                        : activeNav === item.label;
                    return (
                    <button
                      key={item.label}
                      onClick={() => handleNav(item.path)}
                      className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg transition-all duration-200 ${
                        isActive
                          ? 'bg-[#635BFF]/[0.08] text-[#635BFF]'
                          : `${textSecondaryClass} ${isDark ? 'hover:text-white hover:bg-white/[0.04]' : 'hover:text-[#0A2540] hover:bg-[#F7F8FA]'}`
                      }`}
                      type="button"
                    >
                      <item.icon size={20} className="shrink-0" />
                      <span className="text-[14px]" style={{ fontWeight: isActive ? 540 : 440 }}>
                        {item.label}
                      </span>
                    </button>
                    );
                  })}
                  <div className="pt-2 mt-1">
                    <div className="mb-2 flex items-center justify-between px-3">
                      <span className={`text-[11px] uppercase tracking-[0.06em] ${mutedTextClass}`} style={{ fontWeight: 500 }}>
                        Locations
                      </span>
                      <button
                        onClick={() => setShowAddLocation(true)}
                        className={`rounded p-0.5 transition-colors ${hoverSurfaceClass}`}
                        title="Add location"
                        type="button"
                      >
                        <Plus
                          size={13}
                          className="text-[#8898AA] transition-colors hover:text-[#635BFF]"
                        />
                      </button>
                    </div>
                    {!workspaceLocationsLoaded ? (
                      <div className="space-y-2 px-3 py-1">
                        {Array.from({ length: 3 }).map((_, index) => (
                          <div
                            key={index}
                            className={`h-8 animate-pulse rounded-lg ${isDark ? 'bg-white/[0.05]' : 'bg-[#F0F0F5]'}`}
                          />
                        ))}
                      </div>
                    ) : locationShortcuts.length > 0 ? (
                      <div className="pl-3 space-y-1">
                      {locationShortcuts.map((location) => {
                        const isActiveLocation =
                          pathname === location.setupPath || pathname === location.schedulerPath;
                        return (
                          <button
                            key={location.id}
                            onClick={() => handleNav(location.entryPath)}
                            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                              isActiveLocation
                                ? 'bg-[#635BFF]/[0.08] text-[#635BFF]'
                                : `${textSecondaryClass} ${isDark ? 'hover:text-white hover:bg-white/[0.04]' : 'hover:text-[#0A2540] hover:bg-[#F7F8FA]'}`
                            }`}
                            type="button"
                          >
                            <span className="text-[15px]">{location.logo}</span>
                            <span className="text-[13px] truncate" style={{ fontWeight: isActiveLocation ? 540 : 440 }}>
                              {location.name}
                            </span>
                            {typeof location.openShifts === 'number' && location.openShifts > 0 ? (
                              <span className="ml-auto text-[10px] text-[#E5484D] bg-[#E5484D]/10 px-1.5 py-0.5 rounded-full" style={{ fontWeight: 540 }}>
                                {location.openShifts}
                              </span>
                            ) : null}
                          </button>
                        );
                      })}
                      </div>
                    ) : (
                      <button
                        onClick={() => handleNav('/onboarding')}
                        className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-all duration-200 ${textSecondaryClass} ${isDark ? 'hover:text-white hover:bg-white/[0.04]' : 'hover:text-[#0A2540] hover:bg-[#F7F8FA]'}`}
                        type="button"
                      >
                        <span className="text-[15px]">+</span>
                        <span className="text-[13px]" style={{ fontWeight: 440 }}>
                          Set up your first location
                        </span>
                      </button>
                    )}
                  </div>
                </nav>
              </motion.div>
            ) : (
              <motion.div
                key="copilot"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                transition={{ duration: 0.2 }}
                className="flex-1 flex flex-col overflow-hidden"
              >
                <DashboardCopilotSidebar
                  dark={isDark}
                  businessId={
                    activeWorkspaceLocation?.business_id ??
                    preferredBusiness?.business_id ??
                    null
                  }
                  locationHref={
                    activeWorkspaceLocation
                      ? getLocationEntryHref(activeWorkspaceLocation)
                      : null
                  }
                  locationId={activeWorkspaceLocation?.location_id ?? null}
                  locationName={
                    activeWorkspaceLocation?.location_display_name ??
                    activeWorkspaceLocation?.location_name ??
                    null
                  }
                  autoStartSignal={copilotActivationCount}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </aside>

      <div className="flex-1 min-h-screen lg:ml-[300px]">
        <header className={`sticky top-0 z-40 border-b backdrop-blur-xl ${panelBorderClass} ${isDark ? 'bg-[#0A2540]/80' : 'bg-white/80'}`}>
          <div className="flex items-center justify-between h-14 sm:h-16 px-4 sm:px-8">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className={`p-2 rounded-lg transition-colors lg:hidden ${hoverSurfaceClass}`}
                type="button"
              >
                <Menu size={20} className={isDark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'} />
              </button>
              <div className="relative hidden sm:block">
                <Search size={15} className={`absolute left-3 top-1/2 -translate-y-1/2 ${mutedTextClass}`} />
                <input
                  type="text"
                  placeholder="Search..."
                  className={`w-48 md:w-64 pl-9 pr-4 py-2 rounded-lg border text-[12px] transition-all focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${searchFieldClass}`}
                  style={{ fontWeight: 420 }}
                />
              </div>
              <span className={`text-[16px] tracking-[-0.02em] ${textPrimaryClass} lg:hidden sm:hidden`} style={{ fontWeight: 620 }}>
                Backfill
              </span>
            </div>

            <div className="flex items-center gap-1.5 sm:gap-3">
              <div className="relative">
                <button
                  onClick={() => {
                    setShowNotifications((current) => !current);
                    setShowUserMenu(false);
                  }}
                  className={`relative p-2 rounded-lg transition-colors ${hoverSurfaceClass}`}
                  type="button"
                >
                  <Bell size={18} className={isDark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'} />
                  <div className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#E5484D] rounded-full" />
                </button>
                <AnimatePresence>
                  {showNotifications ? (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.96 }}
                      transition={{ duration: 0.2 }}
                      className={`absolute right-0 top-full mt-2 w-[calc(100vw-2rem)] sm:w-80 max-w-80 overflow-hidden border shadow-xl z-[60] ${panelBgClass} ${panelBorderClass} rounded-xl`}
                    >
                      <div className={`px-4 py-3 border-b ${sectionBorderClass}`}>
                        <span className={`text-[13px] ${textPrimaryClass}`} style={{ fontWeight: 560 }}>
                          Notifications
                        </span>
                      </div>
                      {sourceDashboardNotifications.map((notification) => (
                        <div
                          key={notification.id}
                          className={`px-4 py-3 transition-colors border-b last:border-0 ${sectionBorderClass} ${isDark ? 'hover:bg-white/[0.03]' : 'hover:bg-[#F7F8FA]'}`}
                        >
                          <div className="flex items-start gap-2.5">
                            {notification.urgent ? (
                              <AlertCircle size={14} className="text-[#E5484D] mt-0.5 shrink-0" />
                            ) : (
                              <CheckCircle2 size={14} className="text-[#00B893] mt-0.5 shrink-0" />
                            )}
                            <div>
                              <p className={`text-[12px] ${isDark ? 'text-[#C1CED8]' : 'text-[#3E4C59]'}`} style={{ fontWeight: 440 }}>
                                {notification.text}
                              </p>
                              <span className={`text-[11px] ${mutedTextClass}`}>{notification.time} ago</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>

              <div className="relative" ref={userMenuRef}>
                <button
                  onClick={() => {
                    setShowUserMenu((current) => !current);
                    setShowNotifications(false);
                  }}
                  className={`flex items-center gap-2 p-1 pr-2 rounded-full transition-all ${isDark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'}`}
                  type="button"
                >
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0">
                    <span className="text-[11px] text-white" style={{ fontWeight: 600 }}>
                      {initials}
                    </span>
                  </div>
                  <ChevronDown
                    size={13}
                    className={`hidden sm:block text-[#8898AA] transition-transform duration-200 ${showUserMenu ? 'rotate-180' : ''}`}
                  />
                </button>
                <AnimatePresence>
                  {showUserMenu ? (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.96 }}
                      transition={{ duration: 0.2 }}
                      className={`absolute right-0 top-full mt-2 w-[calc(100vw-2rem)] sm:w-64 max-w-64 overflow-hidden border shadow-xl z-[60] ${panelBgClass} ${panelBorderClass} rounded-xl`}
                    >
                      <div className={`px-4 py-3.5 border-b ${sectionBorderClass}`}>
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0">
                            <span className="text-[11px] text-white" style={{ fontWeight: 600 }}>
                              {initials}
                            </span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={`text-[13px] truncate ${textPrimaryClass}`} style={{ fontWeight: 540 }}>
                              {fullName}
                            </p>
                            <p className={`text-[11px] truncate ${mutedTextClass}`} style={{ fontWeight: 420 }}>
                              {email ?? phone ?? 'Phone sign-in'}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="py-1.5">
                        {[
                          {
                            icon: Settings,
                            label: 'Settings',
                            action: () => handleNav(buildSettingsPath('personal', 'profile')),
                          },
                          {
                            icon: LifeBuoy,
                            label: 'Help & support',
                            action: () => setShowUserMenu(false),
                          },
                          {
                            icon: HelpCircle,
                            label: "What's new",
                            action: () => setShowUserMenu(false),
                          },
                        ].map((item) => (
                          <button
                            key={item.label}
                            onClick={item.action}
                            className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`}
                            type="button"
                          >
                            <item.icon size={15} className="text-[#8898AA] shrink-0" />
                            <span className={`text-[12px] ${isDark ? 'text-[#C1CED8]' : 'text-[#3E4C59]'}`} style={{ fontWeight: 480 }}>
                              {item.label}
                            </span>
                          </button>
                        ))}
                      </div>
                      <div className={`border-t py-1.5 ${sectionBorderClass}`}>
                        <button
                          onClick={() => {
                            setShowUserMenu(false);
                            void signOutClientSession();
                          }}
                          className={`group w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${isDark ? 'hover:bg-[#2A1A24]' : 'hover:bg-[#FEF2F2]'}`}
                          type="button"
                        >
                          <LogOut size={15} className="text-[#8898AA] shrink-0 transition-colors group-hover:text-[#E5484D]" />
                          <span className={`text-[12px] transition-colors ${isDark ? 'text-[#C1CED8] group-hover:text-[#E5484D]' : 'text-[#5E6D7A] group-hover:text-[#E5484D]'}`} style={{ fontWeight: 460 }}>
                            Sign out
                          </span>
                        </button>
                      </div>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </header>

        <div className="px-4 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
          {children}
        </div>
      </div>
      <AddLocationModal
        business={preferredBusiness}
        isDark={isDark}
        onClose={() => setShowAddLocation(false)}
        onCreated={(createdLocation, business) => {
          setShowAddLocation(false);
          handleNav(
            buildDashboardLocationBasePathFromAny({
              business_slug: business.business_slug,
              location_slug: createdLocation.slug,
              business_name: business.business_name,
              business_display_name: business.business_display_name,
              location_name: createdLocation.name,
              location_display_name: createdLocation.display_name,
              location_id: createdLocation.id,
            }),
          );
        }}
        open={showAddLocation}
      />
    </div>
  );
}
