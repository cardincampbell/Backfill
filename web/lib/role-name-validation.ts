const COMMON_ROLE_NAMES = [
  "Barista",
  "Bartender",
  "Barback",
  "Cashier",
  "Cook",
  "Dishwasher",
  "Host",
  "Hostess",
  "Line Cook",
  "Manager",
  "Nurse",
  "Prep Cook",
  "Registered Nurse",
  "Retail Associate",
  "Server",
  "Shift Lead",
  "Supervisor",
  "Warehouse Associate",
];

const KNOWN_ROLE_TYPO_SUGGESTIONS = new Map<string, string>([
  ["barrista", "Barista"],
  ["bartendar", "Bartender"],
  ["barbacker", "Barback"],
  ["cashere", "Cashier"],
  ["dishwahser", "Dishwasher"],
  ["hosst", "Host"],
  ["manger", "Manager"],
  ["nuse", "Nurse"],
  ["prepcook", "Prep Cook"],
  ["supevisor", "Supervisor"],
  ["warehosue associate", "Warehouse Associate"],
]);

function normalizeRoleName(value: string) {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function toTitleCaseWord(word: string) {
  if (!word) {
    return word;
  }
  if (/^[A-Z]{2,4}$/.test(word)) {
    return word;
  }
  return word[0].toUpperCase() + word.slice(1).toLowerCase();
}

function levenshteinDistance(left: string, right: string) {
  if (left === right) {
    return 0;
  }
  if (!left.length) {
    return right.length;
  }
  if (!right.length) {
    return left.length;
  }

  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  const current = new Array(right.length + 1).fill(0);

  for (let row = 0; row < left.length; row += 1) {
    current[0] = row + 1;
    for (let column = 0; column < right.length; column += 1) {
      const insertion = current[column] + 1;
      const deletion = previous[column + 1] + 1;
      const substitution = previous[column] + (left[row] === right[column] ? 0 : 1);
      current[column + 1] = Math.min(insertion, deletion, substitution);
    }
    for (let column = 0; column <= right.length; column += 1) {
      previous[column] = current[column];
    }
  }

  return previous[right.length];
}

export function formatRoleName(value: string) {
  return value
    .trim()
    .replace(/\s+/g, " ")
    .split(" ")
    .map((part) =>
      part
        .split("-")
        .map((segment) => toTitleCaseWord(segment))
        .join("-"),
    )
    .join(" ");
}

function findRoleSuggestion(input: string, existingRoleNames: string[]) {
  const normalizedInput = normalizeRoleName(input);
  if (!normalizedInput) {
    return null;
  }

  const directSuggestion = KNOWN_ROLE_TYPO_SUGGESTIONS.get(normalizedInput);
  if (directSuggestion) {
    return directSuggestion;
  }

  if (normalizedInput.length < 5) {
    return null;
  }

  const candidates = Array.from(
    new Set(
      [...existingRoleNames, ...COMMON_ROLE_NAMES].map((candidate) => formatRoleName(candidate)),
    ),
  );

  let bestMatch: string | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const candidate of candidates) {
    const normalizedCandidate = normalizeRoleName(candidate);
    if (normalizedCandidate === normalizedInput) {
      continue;
    }
    if (normalizedCandidate[0] !== normalizedInput[0]) {
      continue;
    }
    const distance = levenshteinDistance(normalizedInput, normalizedCandidate);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestMatch = candidate;
    }
  }

  if (!bestMatch) {
    return null;
  }

  const maxDistance = normalizedInput.length >= 8 ? 2 : 1;
  return bestDistance <= maxDistance ? bestMatch : null;
}

export type RoleNameValidationResult =
  | {
      ok: true;
      roleName: string;
    }
  | {
      ok: false;
      message: string;
    };

export function validateCustomRoleName(
  input: string,
  existingRoleNames: string[],
): RoleNameValidationResult {
  const roleName = formatRoleName(input);
  if (!roleName) {
    return { ok: false, message: "Enter a role name." };
  }

  const suggestion = findRoleSuggestion(roleName, existingRoleNames);
  if (suggestion) {
    return {
      ok: false,
      message: `Did you mean "${suggestion}"?`,
    };
  }

  return { ok: true, roleName };
}
