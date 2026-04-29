import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { EmployeeEditorDrawer, type EmployeeEditorSeed } from "./EmployeeEditorDrawer";

const mockCreateBusinessRole = vi.fn();
const mockDeleteEmployee = vi.fn();
const mockGetEmployeeAvailability = vi.fn();
const mockGetEmployeeDeleteReadiness = vi.fn();
const mockGetEmployeeProfile = vi.fn();
const mockListWorkPermitTemplates = vi.fn();
const mockReplaceEmployeeAvailability = vi.fn();
const mockUpdateEmployee = vi.fn();

vi.mock("motion/react", () => {
  const MotionDiv = ({ children, ...props }: Record<string, unknown>) => {
    const {
      animate: _animate,
      exit: _exit,
      initial: _initial,
      layout: _layout,
      transition: _transition,
      ...rest
    } = props;
    return <div {...rest}>{children as React.ReactNode}</div>;
  };
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: {
      div: MotionDiv,
    },
  };
});

vi.mock("./AvailabilityEditorPanel", async () => {
  const actual = await vi.importActual<typeof import("./AvailabilityEditorPanel")>(
    "./AvailabilityEditorPanel",
  );
  return {
    ...actual,
    AvailabilityEditorPanel: () => <div data-testid="availability-editor" />,
  };
});

vi.mock("@/lib/api/businesses", () => ({
  createBusinessRole: (...args: unknown[]) => mockCreateBusinessRole(...args),
}));

vi.mock("@/lib/api/workforce", () => ({
  deleteEmployee: (...args: unknown[]) => mockDeleteEmployee(...args),
  getEmployeeAvailability: (...args: unknown[]) => mockGetEmployeeAvailability(...args),
  getEmployeeDeleteReadiness: (...args: unknown[]) => mockGetEmployeeDeleteReadiness(...args),
  getEmployeeProfile: (...args: unknown[]) => mockGetEmployeeProfile(...args),
  listWorkPermitTemplates: (...args: unknown[]) => mockListWorkPermitTemplates(...args),
  replaceEmployeeAvailability: (...args: unknown[]) => mockReplaceEmployeeAvailability(...args),
  updateEmployee: (...args: unknown[]) => mockUpdateEmployee(...args),
}));

function buildEmployeeProfile(overrides: Record<string, unknown> = {}) {
  return {
    id: "emp_123",
    business_id: "biz_123",
    primary_location_id: "loc_1",
    primary_location_name: "Downtown",
    primary_role_id: "role_1",
    primary_role_name: "Cashier",
    external_ref: null,
    employee_number: null,
    full_name: "Jamie Rivera",
    preferred_name: null,
    phone_e164: "+15555550123",
    email: "jamie@example.com",
    base_hourly_rate_cents: 1800,
    date_of_birth: "2010-02-01",
    minor_school_status: "in_session",
    work_permit_number: "WP-123",
    work_permit_effective_start_on: "2026-04-01",
    work_permit_expires_on: "2026-06-30",
    work_permit_max_daily_minutes: null,
    work_permit_max_weekly_minutes: null,
    work_permit_earliest_start_local_time: null,
    work_permit_latest_end_local_time: null,
    reliability_score: 0.95,
    status: "active",
    employment_type: "part_time",
    hire_date: null,
    termination_date: null,
    notes: null,
    employee_metadata: {},
    notification_preferences: {
      schedule_publish_email_enabled: true,
      schedule_publish_sms_enabled: true,
      email_opted_out_at: null,
      sms_opted_out_at: null,
      email_opt_out_reason: null,
      sms_opt_out_reason: null,
    },
    role_ids: ["role_1"],
    role_names: ["Cashier"],
    location_ids: ["loc_1"],
    location_names: ["Downtown"],
    created_at: "2026-04-28T00:00:00Z",
    updated_at: "2026-04-28T00:00:00Z",
    roles: [
      {
        id: "assign_role_1",
        employee_id: "emp_123",
        role_id: "role_1",
        role_code: "cashier",
        role_name: "Cashier",
        proficiency_level: 1,
        is_primary: true,
        acquired_at: null,
        role_metadata: {},
        created_at: "2026-04-28T00:00:00Z",
        updated_at: "2026-04-28T00:00:00Z",
      },
    ],
    locations: [
      {
        id: "assign_loc_1",
        employee_id: "emp_123",
        location_id: "loc_1",
        location_name: "Downtown",
        location_slug: "downtown",
        is_primary: true,
        access_level: "approved",
        location_source: null,
        can_cover_last_minute: true,
        can_blast: true,
        travel_radius_miles: null,
        location_metadata: {},
        created_at: "2026-04-28T00:00:00Z",
        updated_at: "2026-04-28T00:00:00Z",
      },
    ],
    work_permits: [
      {
        id: "permit_1",
        employee_id: "emp_123",
        permit_number: "WP-123",
        issuing_authority: "CA",
        issued_on: "2026-03-15",
        effective_start_date: "2026-04-01",
        effective_end_date: "2026-06-30",
        max_daily_minutes: null,
        max_weekly_minutes: null,
        earliest_start_local_time: null,
        latest_end_local_time: null,
        rule_profile: {
          template_code: "ca_14_15_school_enrolled_v1",
        },
        permit_metadata: {},
        created_at: "2026-04-28T00:00:00Z",
        updated_at: "2026-04-28T00:00:00Z",
      },
    ],
    ...overrides,
  };
}

const defaultSeed: EmployeeEditorSeed = {
  id: "emp_123",
  full_name: "Jamie Rivera",
  preferred_name: null,
  email: "jamie@example.com",
  phone_e164: "+15555550123",
  primary_location_id: "loc_1",
  primary_role_id: "role_1",
  role_ids: ["role_1"],
  role_names: ["Cashier"],
  location_ids: ["loc_1"],
  location_names: ["Downtown"],
  reliability_score: 0.95,
  status: "active",
};

const defaultLocations = [
  {
    id: "loc_1",
    business_id: "biz_123",
    name: "Downtown",
    display_name: "Downtown",
    slug: "downtown",
    timezone: "America/Los_Angeles",
    status: "active",
    metadata: {},
    created_at: "2026-04-28T00:00:00Z",
    updated_at: "2026-04-28T00:00:00Z",
  },
];

const defaultRoles = [
  {
    id: "role_1",
    business_id: "biz_123",
    name: "Cashier",
    code: "cashier",
    active: true,
    metadata: {},
    created_at: "2026-04-28T00:00:00Z",
    updated_at: "2026-04-28T00:00:00Z",
  },
];

function renderDrawer() {
  return render(
    <EmployeeEditorDrawer
      businessId="biz_123"
      dark={false}
      employee={defaultSeed}
      locations={defaultLocations as never}
      onClose={vi.fn()}
      onSaved={vi.fn()}
      roles={defaultRoles as never}
    />,
  );
}

describe("EmployeeEditorDrawer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreateBusinessRole.mockResolvedValue({
      decision: "created_new",
      role: defaultRoles[0],
    });
    mockDeleteEmployee.mockResolvedValue({ deleted: true, employee_id: "emp_123" });
    mockGetEmployeeAvailability.mockResolvedValue({
      employee_id: "emp_123",
      employee_name: "Jamie Rivera",
      timezone: "America/Los_Angeles",
      rules: [],
    });
    mockGetEmployeeDeleteReadiness.mockResolvedValue({
      business_id: "biz_123",
      employee_id: "emp_123",
      can_delete: true,
      reason: null,
    });
    mockListWorkPermitTemplates.mockResolvedValue([
      {
        code: "ca_14_15_school_enrolled_v1",
        label: "California ages 14-15 while school enrolled",
        description: "3 hours on schooldays, 8 hours on non-schooldays.",
        jurisdiction_code: "US-CA",
        source_url: "https://www.dir.ca.gov/dlse/MinorsSummaryCharts.pdf",
        rule_profile: {
          template_code: "ca_14_15_school_enrolled_v1",
          daily_max_minutes_school_day: 180,
        },
      },
      {
        code: "ca_16_17_school_required_v1",
        label: "California ages 16-17 while school required",
        description: "4 hours on schooldays, 8 hours on non-schooldays.",
        jurisdiction_code: "US-CA",
        source_url: "https://www.dir.ca.gov/dlse/MinorsSummaryCharts.pdf",
        rule_profile: {
          template_code: "ca_16_17_school_required_v1",
          daily_max_minutes_school_day: 240,
        },
      },
    ]);
    mockReplaceEmployeeAvailability.mockResolvedValue({
      employee_id: "emp_123",
      employee_name: "Jamie Rivera",
      timezone: "America/Los_Angeles",
      rules: [],
    });
  });

  it("sends youth compliance updates through updateEmployee", async () => {
    const updatedProfile = buildEmployeeProfile({
      minor_school_status: "summer_break",
      work_permits: [
        {
          id: "permit_1",
          employee_id: "emp_123",
          permit_number: "WP-123",
          issuing_authority: "CA",
          issued_on: "2026-03-15",
          effective_start_date: "2026-04-01",
          effective_end_date: "2026-06-30",
          max_daily_minutes: null,
          max_weekly_minutes: null,
          earliest_start_local_time: null,
          latest_end_local_time: null,
          rule_profile: {
            template_code: "ca_16_17_school_required_v1",
          },
          permit_metadata: {},
          created_at: "2026-04-28T00:00:00Z",
          updated_at: "2026-04-28T00:00:00Z",
        },
      ],
    });
    mockGetEmployeeProfile.mockResolvedValue(buildEmployeeProfile());
    mockUpdateEmployee.mockResolvedValue(updatedProfile);

    renderDrawer();

    await screen.findByLabelText(/permit template/i);

    fireEvent.change(screen.getByLabelText(/school status/i), {
      target: { value: "summer_break" },
    });
    fireEvent.change(screen.getByLabelText(/permit template/i), {
      target: { value: "ca_16_17_school_required_v1" },
    });

    fireEvent.click(screen.getByRole("button", { name: /save 2 changes/i }));

    await waitFor(() => expect(mockUpdateEmployee).toHaveBeenCalledOnce());
    expect(mockUpdateEmployee).toHaveBeenCalledWith(
      "biz_123",
      "emp_123",
      expect.objectContaining({
        date_of_birth: "2010-02-01",
        minor_school_status: "summer_break",
        work_permits: [
          expect.objectContaining({
            permit_number: "WP-123",
            rule_profile: expect.objectContaining({
              template_code: "ca_16_17_school_required_v1",
            }),
          }),
        ],
      }),
    );
  });

  it("blocks partial permit edits without a permit number", async () => {
    mockGetEmployeeProfile.mockResolvedValue(
      buildEmployeeProfile({
        date_of_birth: null,
        minor_school_status: null,
        work_permit_number: null,
        work_permit_effective_start_on: null,
        work_permit_expires_on: null,
        work_permits: [],
      }),
    );

    renderDrawer();

    await screen.findByLabelText(/permit template/i);

    fireEvent.change(screen.getByLabelText(/permit template/i), {
      target: { value: "ca_14_15_school_enrolled_v1" },
    });

    expect(
      await screen.findByText(/permit number is required before permit dates or a permit template can be saved/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save 1 change/i })).toBeDisabled();
  });
});
