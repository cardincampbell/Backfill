export type SourceDashboardActivityType = "success" | "warning" | "info";

export type SourceDashboardLocationActivityItem = {
  text: string;
  time: string;
  type: SourceDashboardActivityType;
};

export type SourceDashboardTopStaffEntry = {
  name: string;
  role: string;
  shifts: number;
  rating: number;
};

export type SourceDashboardLocation = {
  id: number;
  slug: string;
  name: string;
  type: string;
  logo: string;
  color: string;
  activeShifts: number;
  totalStaff: number;
  fillRate: number;
  openShifts: number;
  revenue: string;
  trend: number;
  weeklyShifts: number[];
  recentActivity: SourceDashboardLocationActivityItem[];
  topStaff: SourceDashboardTopStaffEntry[];
};

export type SourceDashboardNotification = {
  id: number;
  text: string;
  time: string;
  urgent: boolean;
};

export type SourceDashboardActivityIconKey =
  | "alert-circle"
  | "calendar-plus"
  | "calendar-x"
  | "check-circle"
  | "file-text"
  | "refresh-cw"
  | "shield-check"
  | "user-minus"
  | "user-plus";

export type SourceDashboardActivityItem = {
  id: number;
  text: string;
  time: string;
  type: SourceDashboardActivityType;
  location: string;
  locationEmoji: string;
  category: string;
  iconKey: SourceDashboardActivityIconKey;
};

export type SourceDashboardCuratedRoleCategory =
  | "Healthcare"
  | "Senior Care"
  | "Hospitality";

export type SourceDashboardCuratedRole = {
  name: string;
  category: SourceDashboardCuratedRoleCategory;
};

export const sourceDashboardLocations: SourceDashboardLocation[] = [
  {
    id: 1,
    slug: "downtown-medical-center",
    name: "Downtown Medical Center",
    type: "Healthcare",
    logo: "\u{1F3E5}",
    color: "#635BFF",
    activeShifts: 24,
    totalStaff: 48,
    fillRate: 96,
    openShifts: 3,
    revenue: "$12,400",
    trend: 8.2,
    weeklyShifts: [18, 22, 20, 24, 19, 21, 24],
    recentActivity: [
      {
        text: "Sarah M. accepted Night Shift — ICU",
        time: "2 min ago",
        type: "success",
      },
      {
        text: "3 open shifts posted for ER coverage",
        time: "18 min ago",
        type: "info",
      },
      {
        text: "Marcus T. called out — Shift reassigned",
        time: "1 hr ago",
        type: "warning",
      },
      {
        text: "Weekly compliance report generated",
        time: "2 hrs ago",
        type: "info",
      },
    ],
    topStaff: [
      { name: "Sarah Martinez", role: "RN", shifts: 18, rating: 4.9 },
      { name: "James Chen", role: "LPN", shifts: 15, rating: 4.8 },
      { name: "Aisha Patel", role: "CNA", shifts: 22, rating: 4.7 },
    ],
  },
  {
    id: 2,
    slug: "sunrise-senior-living",
    name: "Sunrise Senior Living",
    type: "Senior Care",
    logo: "\u{1F305}",
    color: "#00B893",
    activeShifts: 18,
    totalStaff: 32,
    fillRate: 91,
    openShifts: 5,
    revenue: "$8,750",
    trend: 12.5,
    weeklyShifts: [14, 16, 15, 18, 17, 16, 18],
    recentActivity: [
      {
        text: "New caregiver onboarded successfully",
        time: "15 min ago",
        type: "success",
      },
      {
        text: "5 weekend shifts still need coverage",
        time: "45 min ago",
        type: "warning",
      },
    ],
    topStaff: [
      { name: "Emily Ross", role: "Caregiver", shifts: 20, rating: 4.9 },
      { name: "David Kim", role: "CNA", shifts: 16, rating: 4.6 },
    ],
  },
  {
    id: 3,
    slug: "bay-area-staffing-co",
    name: "Bay Area Staffing Co.",
    type: "Staffing Agency",
    logo: "\u{1F3E2}",
    color: "#FF6B35",
    activeShifts: 42,
    totalStaff: 120,
    fillRate: 88,
    openShifts: 12,
    revenue: "$34,200",
    trend: 5.1,
    weeklyShifts: [35, 38, 40, 42, 39, 41, 42],
    recentActivity: [
      {
        text: "12 shifts broadcast to available staff",
        time: "1 hr ago",
        type: "info",
      },
    ],
    topStaff: [{ name: "Carlos Rivera", role: "Temp RN", shifts: 24, rating: 4.8 }],
  },
  {
    id: 4,
    slug: "coastal-hospitality-group",
    name: "Coastal Hospitality Group",
    type: "Hospitality",
    logo: "\u{1F3E8}",
    color: "#3B82F6",
    activeShifts: 8,
    totalStaff: 15,
    fillRate: 100,
    openShifts: 0,
    revenue: "$4,100",
    trend: -2.3,
    weeklyShifts: [6, 7, 8, 8, 7, 8, 8],
    recentActivity: [
      {
        text: "All shifts fully staffed for the week",
        time: "3 hrs ago",
        type: "success",
      },
    ],
    topStaff: [{ name: "Mia Johnson", role: "Server Lead", shifts: 12, rating: 4.9 }],
  },
];

export const sourceDashboardNotifications: SourceDashboardNotification[] = [
  {
    id: 1,
    text: "3 shifts need coverage at Downtown Medical",
    time: "2m",
    urgent: true,
  },
  {
    id: 2,
    text: "New staff member onboarded at Sunrise Senior",
    time: "15m",
    urgent: false,
  },
  {
    id: 3,
    text: "Weekly report ready for Bay Area Staffing",
    time: "1h",
    urgent: false,
  },
];

export const sourceDashboardActivity: SourceDashboardActivityItem[] = [
  {
    id: 1,
    text: "Sarah M. accepted Night Shift — ICU",
    time: "2 min ago",
    type: "success",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Shifts",
    iconKey: "check-circle",
  },
  {
    id: 2,
    text: "3 open shifts posted for ER coverage",
    time: "18 min ago",
    type: "info",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Shifts",
    iconKey: "calendar-plus",
  },
  {
    id: 3,
    text: "New caregiver onboarded successfully",
    time: "25 min ago",
    type: "success",
    location: "Sunrise Senior Living",
    locationEmoji: "\u{1F305}",
    category: "Team",
    iconKey: "user-plus",
  },
  {
    id: 4,
    text: "5 weekend shifts still need coverage",
    time: "45 min ago",
    type: "warning",
    location: "Sunrise Senior Living",
    locationEmoji: "\u{1F305}",
    category: "Shifts",
    iconKey: "alert-circle",
  },
  {
    id: 5,
    text: "Marcus T. called out — Shift reassigned",
    time: "1 hr ago",
    type: "warning",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Shifts",
    iconKey: "refresh-cw",
  },
  {
    id: 6,
    text: "12 shifts broadcast to available staff",
    time: "1 hr ago",
    type: "info",
    location: "Bay Area Staffing Co.",
    locationEmoji: "\u{1F3E2}",
    category: "Shifts",
    iconKey: "calendar-plus",
  },
  {
    id: 7,
    text: "Weekly compliance report generated",
    time: "2 hrs ago",
    type: "info",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Reports",
    iconKey: "file-text",
  },
  {
    id: 8,
    text: "All shifts fully staffed for the week",
    time: "3 hrs ago",
    type: "success",
    location: "Coastal Hospitality Group",
    locationEmoji: "\u{1F3E8}",
    category: "Shifts",
    iconKey: "check-circle",
  },
  {
    id: 9,
    text: "James Chen credentials verified",
    time: "3 hrs ago",
    type: "success",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Compliance",
    iconKey: "shield-check",
  },
  {
    id: 10,
    text: "Overtime limit reached for Carlos Rivera",
    time: "4 hrs ago",
    type: "warning",
    location: "Bay Area Staffing Co.",
    locationEmoji: "\u{1F3E2}",
    category: "Compliance",
    iconKey: "alert-circle",
  },
  {
    id: 11,
    text: "Emily Ross promoted to Shift Lead",
    time: "5 hrs ago",
    type: "success",
    location: "Sunrise Senior Living",
    locationEmoji: "\u{1F305}",
    category: "Team",
    iconKey: "user-plus",
  },
  {
    id: 12,
    text: "Night shift coverage confirmed — Med-Surg",
    time: "5 hrs ago",
    type: "success",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Shifts",
    iconKey: "check-circle",
  },
  {
    id: 13,
    text: "4 new applications received",
    time: "6 hrs ago",
    type: "info",
    location: "Bay Area Staffing Co.",
    locationEmoji: "\u{1F3E2}",
    category: "Team",
    iconKey: "user-plus",
  },
  {
    id: 14,
    text: "Weekend schedule published",
    time: "8 hrs ago",
    type: "info",
    location: "Coastal Hospitality Group",
    locationEmoji: "\u{1F3E8}",
    category: "Shifts",
    iconKey: "calendar-plus",
  },
  {
    id: 15,
    text: "Break compliance audit passed",
    time: "9 hrs ago",
    type: "success",
    location: "Sunrise Senior Living",
    locationEmoji: "\u{1F305}",
    category: "Compliance",
    iconKey: "shield-check",
  },
  {
    id: 16,
    text: "Lisa Park removed from active roster",
    time: "10 hrs ago",
    type: "warning",
    location: "Bay Area Staffing Co.",
    locationEmoji: "\u{1F3E2}",
    category: "Team",
    iconKey: "user-minus",
  },
  {
    id: 17,
    text: "Shift swap approved: Aisha ↔ David",
    time: "12 hrs ago",
    type: "info",
    location: "Downtown Medical Center",
    locationEmoji: "\u{1F3E5}",
    category: "Shifts",
    iconKey: "refresh-cw",
  },
  {
    id: 18,
    text: "Monthly payroll report exported",
    time: "14 hrs ago",
    type: "info",
    location: "Bay Area Staffing Co.",
    locationEmoji: "\u{1F3E2}",
    category: "Reports",
    iconKey: "file-text",
  },
  {
    id: 19,
    text: "2 shifts cancelled due to low census",
    time: "1 day ago",
    type: "warning",
    location: "Sunrise Senior Living",
    locationEmoji: "\u{1F305}",
    category: "Shifts",
    iconKey: "calendar-x",
  },
  {
    id: 20,
    text: "New location onboarding completed",
    time: "1 day ago",
    type: "success",
    location: "Coastal Hospitality Group",
    locationEmoji: "\u{1F3E8}",
    category: "Team",
    iconKey: "check-circle",
  },
];

export const sourceDashboardCuratedRoles: SourceDashboardCuratedRole[] = [
  { name: "RN", category: "Healthcare" },
  { name: "LPN", category: "Healthcare" },
  { name: "CNA", category: "Healthcare" },
  { name: "NP", category: "Healthcare" },
  { name: "PA", category: "Healthcare" },
  { name: "Medical Assistant", category: "Healthcare" },
  { name: "Phlebotomist", category: "Healthcare" },
  { name: "Respiratory Therapist", category: "Healthcare" },
  { name: "Radiology Tech", category: "Healthcare" },
  { name: "Surgical Tech", category: "Healthcare" },
  { name: "EMT", category: "Healthcare" },
  { name: "Caregiver", category: "Senior Care" },
  { name: "Server Lead", category: "Hospitality" },
  { name: "Host", category: "Hospitality" },
  { name: "Bartender", category: "Hospitality" },
  { name: "Line Cook", category: "Hospitality" },
];

export const sourceDashboardRoleCategories: SourceDashboardCuratedRoleCategory[] =
  ["Healthcare", "Senior Care", "Hospitality"];

export function findSourceDashboardLocationBySlug(
  slug: string,
): SourceDashboardLocation | null {
  return (
    sourceDashboardLocations.find((location) => location.slug === slug) ?? null
  );
}
