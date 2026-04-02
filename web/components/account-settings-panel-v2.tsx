"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  updateV2AccountProfile,
  type V2AuthMeResponse,
  type V2AuthUser,
} from "@/lib/api/v2-auth";
import { signOutClientSession } from "@/lib/auth/client-signout";

type AccountSettingsPanelV2Props = {
  session: V2AuthMeResponse;
};

function getInitials(label: string): string {
  const parts = label
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "B";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function profileTitle(user: V2AuthUser): string {
  return user.full_name?.trim() || user.email?.trim() || "Backfill account";
}

export function AccountSettingsPanelV2({
  session,
}: AccountSettingsPanelV2Props) {
  const router = useRouter();
  const [user, setUser] = useState(session.user);
  const [fullName, setFullName] = useState(session.user.full_name ?? "");
  const [email, setEmail] = useState(session.user.email ?? "");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  const [signingOut, startSignOutTransition] = useTransition();

  const trimmedName = fullName.trim();
  const normalizedEmail = normalizeEmail(email);
  const currentName = user.full_name?.trim() ?? "";
  const currentEmail = normalizeEmail(user.email ?? "");
  const hasChanges = trimmedName !== currentName || normalizedEmail !== currentEmail;
  const canSave =
    Boolean(trimmedName) && isValidEmail(email) && hasChanges && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setFeedback(null);
    try {
      const response = await updateV2AccountProfile({
        full_name: trimmedName,
        email: normalizedEmail,
      });
      setUser(response.user);
      setFullName(response.user.full_name ?? "");
      setEmail(response.user.email ?? "");
      setFeedback({ type: "success", message: "Account details updated." });
      router.refresh();
    } catch (error) {
      setFeedback({
        type: "error",
        message:
          error instanceof Error ? error.message : "Could not update your account.",
      });
    } finally {
      setSaving(false);
    }
  }

  function handleSignOut() {
    startSignOutTransition(async () => {
      await signOutClientSession("/login");
    });
  }

  return (
    <div className="account-settings-shell">
      <header className="workspace-shell-head">
        <div className="workspace-shell-head-copy">
          <span className="workspace-shell-brand">Account</span>
          <h1>Your profile</h1>
          <p>
            Update the personal details tied to your Backfill sign-in. Workspace
            and location controls live outside this page.
          </p>
        </div>
      </header>

      <section className="account-settings-summary">
        <div className="account-settings-summary-avatar">
          {getInitials(profileTitle(user))}
        </div>
        <div className="account-settings-summary-copy">
          <strong>{profileTitle(user)}</strong>
          <span>{user.email?.trim() || "Add an email for invites and alerts."}</span>
        </div>
      </section>

      <div className="account-settings-grid">
        <section className="settings-card">
          <div className="settings-card-header">Profile</div>
          <div className="settings-card-body">
            <label className="field">
              <span>Full name</span>
              <input
                autoComplete="name"
                onChange={(event) => setFullName(event.target.value)}
                type="text"
                value={fullName}
              />
            </label>

            <label className="field">
              <span>Email</span>
              <input
                autoComplete="email"
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                value={email}
              />
            </label>

            <div className="muted">
              Use the email where you want invites, workspace alerts, and admin
              updates to arrive.
            </div>

            {feedback ? (
              <div
                className="account-locations-feedback"
                data-tone={feedback.type}
                role="status"
              >
                {feedback.message}
              </div>
            ) : null}

            <div className="v2-manager-panel-actions">
              <span className="muted">
                {hasChanges
                  ? "Save to update the profile shown across your Backfill account."
                  : "Your profile details are up to date."}
              </span>
              <button
                className="button button-small"
                disabled={!canSave}
                onClick={handleSave}
                type="button"
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </section>

        <section className="settings-card">
          <div className="settings-card-header">Sign-in</div>
          <div className="settings-card-body">
            <div className="account-settings-info-list">
              <div className="account-settings-info-row">
                <span>Phone username</span>
                <strong>{user.primary_phone_e164 ?? "Not set"}</strong>
              </div>
              <div className="account-settings-info-row">
                <span>Phone verification</span>
                <strong>{user.is_phone_verified ? "Verified" : "Pending"}</strong>
              </div>
              <div className="account-settings-info-row">
                <span>Last sign-in</span>
                <strong>{formatTimestamp(user.last_sign_in_at)}</strong>
              </div>
              <div className="account-settings-info-row">
                <span>Account created</span>
                <strong>{formatTimestamp(user.created_at)}</strong>
              </div>
            </div>

            <div className="account-settings-note">
              Your phone number is your username in Backfill. Phone changes are
              not self-serve yet.
            </div>

            <div className="v2-manager-panel-actions">
              <span className="muted">
                End this session if you are switching devices or sharing access.
              </span>
              <button
                className="button-secondary button-small"
                disabled={signingOut}
                onClick={handleSignOut}
                type="button"
              >
                {signingOut ? "Signing out…" : "Sign out"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
