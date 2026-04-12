"use client";

import type { EmployeeProfile, EmployeeSummary } from "@/lib/api/workforce";
import type { LocationRoleAssignment } from "@/lib/api/businesses";

export function employeeDisplayName(
  employee: Pick<EmployeeSummary, "full_name" | "preferred_name">,
) {
  return employee.preferred_name?.trim() || employee.full_name;
}

export function employeeInitials(name: string) {
  return (
    name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "?"
  );
}

export function employeeHasAssignedRoles(
  employee: Pick<EmployeeSummary, "role_ids">,
) {
  return employee.role_ids.length > 0;
}

export function employeeEligibilityReason(
  employee: Pick<EmployeeSummary, "role_ids" | "location_ids">,
) {
  const missingRole = employee.role_ids.length === 0;
  const missingLocation = employee.location_ids.length === 0;

  if (missingRole && missingLocation) {
    return "Missing role and location assignment";
  }
  if (missingRole) {
    return "Missing role assignment";
  }
  if (missingLocation) {
    return "Missing location assignment";
  }
  return "Missing scheduling requirements";
}

export function employeeAssignedHere(
  employee: Pick<EmployeeSummary, "location_ids">,
  locationId: string,
) {
  return employee.location_ids.includes(locationId);
}

export function buildEmployeeLocationAssignments(
  employee: Pick<EmployeeSummary, "location_ids" | "primary_location_id">,
  locationId: string,
  includeLocation: boolean,
) {
  const nextLocationIds = employee.location_ids.filter((item) => item !== locationId);
  if (includeLocation) {
    nextLocationIds.push(locationId);
  }

  if (!nextLocationIds.length) {
    return [];
  }

  const preservedPrimaryLocationId =
    employee.primary_location_id && nextLocationIds.includes(employee.primary_location_id)
      ? employee.primary_location_id
      : includeLocation
        ? locationId
        : nextLocationIds[0];

  return nextLocationIds.map((item) => ({
    location_id: item,
    is_primary: item === preservedPrimaryLocationId,
  }));
}

export function buildInheritedLocationRoleIds(
  assignments: Pick<LocationRoleAssignment, "role_id">[],
  employees: Pick<EmployeeSummary, "id" | "role_ids">[],
  selectedEmployeeIds: string[],
) {
  return Array.from(
    new Set([
      ...assignments.map((assignment) => assignment.role_id),
      ...employees
        .filter((employee) => selectedEmployeeIds.includes(employee.id))
        .flatMap((employee) => employee.role_ids),
    ]),
  );
}

export function countEmployeeAssignmentChanges(
  initialEmployeeIds: string[],
  nextEmployeeIds: string[],
) {
  const initial = new Set(initialEmployeeIds);
  const next = new Set(nextEmployeeIds);
  let count = 0;

  initial.forEach((employeeId) => {
    if (!next.has(employeeId)) {
      count += 1;
    }
  });
  next.forEach((employeeId) => {
    if (!initial.has(employeeId)) {
      count += 1;
    }
  });

  return count;
}

export function mergeUpdatedEmployees(
  currentEmployees: EmployeeSummary[],
  updatedEmployees: EmployeeProfile[],
) {
  if (!updatedEmployees.length) {
    return currentEmployees;
  }
  const updatedById = new Map(updatedEmployees.map((employee) => [employee.id, employee]));
  return currentEmployees.map((employee) => updatedById.get(employee.id) ?? employee);
}
