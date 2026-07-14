"use client";

import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";

import styles from "./page.module.css";

export function AuthControls() {
  return (
    <div className={styles.authControls} aria-label="Account controls">
      <Show when="signed-out">
        <SignInButton mode="modal">
          <button className={styles.authButton} type="button">
            Sign in
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className={styles.authButtonSecondary} type="button">
            Sign up
          </button>
        </SignUpButton>
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </div>
  );
}
