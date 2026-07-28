import Image from "next/image";

import styles from "./stonegate-logo.module.css";

type StonegateLogoProps = {
  className?: string;
  inverse?: boolean;
};

export function StonegateLogo({
  className = "",
  inverse = false,
}: StonegateLogoProps) {
  return (
    <span
      aria-label="Stonegate Home Buyers"
      className={`${styles.logo} ${inverse ? styles.inverse : ""} ${className}`}
      role="img"
    >
      <Image
        alt=""
        aria-hidden="true"
        className={styles.mark}
        height={512}
        src="/brand/stonegate-mark.png"
        width={512}
      />
      <span aria-hidden="true" className={styles.wordmark}>
        <strong>STONEGATE</strong>
        <span>HOME BUYERS</span>
      </span>
    </span>
  );
}
