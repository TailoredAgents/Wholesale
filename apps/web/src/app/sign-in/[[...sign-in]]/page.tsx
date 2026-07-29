import { SignIn } from "@clerk/nextjs";
import type { Metadata } from "next";

import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Staff Sign In | Stonegate Home Buyers",
  robots: {
    index: false,
    follow: false,
    noarchive: true,
  },
};

export default function SignInPage() {
  return (
    <main className={styles.page}>
      <SignIn />
    </main>
  );
}
