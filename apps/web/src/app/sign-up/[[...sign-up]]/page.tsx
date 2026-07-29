import { SignUp } from "@clerk/nextjs";
import type { Metadata } from "next";

import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Staff Account Setup | Stonegate Home Buyers",
  robots: {
    index: false,
    follow: false,
    noarchive: true,
  },
};

export default function SignUpPage() {
  return (
    <main className={styles.page}>
      <SignUp />
    </main>
  );
}
