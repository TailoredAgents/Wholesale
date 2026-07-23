"use client";

import { Show, SignInButton, UserButton } from "@clerk/nextjs";

import styles from "./page.module.css";

export function AuthControls({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`${styles.authControls} ${compact ? styles.authControlsCompact : ""}`}
      aria-label="Account controls"
      role="group"
    >
      <Show when="signed-out">
        <SignInButton mode="modal">
          <button className={styles.authButton} type="button">
            Sign in
          </button>
        </SignInButton>
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </div>
  );
}
