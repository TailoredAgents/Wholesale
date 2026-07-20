import type { Metadata } from "next";
import Link from "next/link";

import styles from "../legal-page.module.css";
import { PublicSiteFooter } from "../public-site-footer";

export const metadata: Metadata = {
  title: "Privacy Policy | Stonegate Home Buyers",
  description: "How Stonegate Home Buyers collects, uses, and protects personal information.",
};

export default function PrivacyPolicyPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Stonegate Home Buyers
        </Link>
        <nav aria-label="Primary navigation">
          <Link href="/get-a-cash-offer">Get a cash offer</Link>
          <Link href="/terms">Terms &amp; Conditions</Link>
        </nav>
      </header>

      <article className={styles.content}>
        <p className={styles.eyebrow}>Stonegate Home Buyers</p>
        <h1>Privacy Policy</h1>
        <p className={styles.effective}>Effective July 18, 2026</p>
        <p className={styles.intro}>
          This Privacy Policy explains how Stonegate Home Buyers collects, uses, discloses, and
          protects information when you visit our website, request a property offer, call us, or
          communicate with us.
        </p>

        <section>
          <h2>Information we collect</h2>
          <ul>
            <li>
              Contact information, including your name, phone number, email address, and preferred
              contact method.
            </li>
            <li>
              Property information, including address, condition, occupancy, repair needs,
              mortgage details you choose to provide, and your desired selling timeline.
            </li>
            <li>
              Communications, including emails, text messages, call details, notes, and information
              you provide during conversations.
            </li>
            <li>
              Website and device information, including IP address, browser details, referring
              page, advertising attribution, and interactions with our forms.
            </li>
          </ul>
        </section>

        <section>
          <h2>How we use information</h2>
          <ul>
            <li>Review your property and respond to your cash-offer request.</li>
            <li>Schedule appointments and communicate about the property or offer process.</li>
            <li>Operate, secure, analyze, and improve our website and business systems.</li>
            <li>Maintain consent, suppression, transaction, and compliance records.</li>
            <li>Prevent fraud, enforce our terms, and meet legal obligations.</li>
          </ul>
        </section>

        <section className={styles.smsNotice}>
          <h2>Mobile information and text-message consent</h2>
          <p>
            The categories of disclosure described in this policy exclude text-message originator
            opt-in data and consent. We do not sell, rent, or share mobile phone information,
            text-message opt-in data, or consent with third parties or affiliates for their
            marketing or promotional purposes. We may provide mobile information only to service
            providers that help us deliver and support our messaging program, or when required by
            law. Those providers may use the information only to provide services to Stonegate Home
            Buyers.
          </p>
        </section>

        <section>
          <h2>How we disclose information</h2>
          <p>
            We may disclose information to vendors that provide hosting, communications, property
            data, analytics, security, professional, or transaction-support services on our behalf.
            We may also disclose information to title companies, attorneys, contractors, buyers,
            or other parties when reasonably necessary to evaluate or complete a transaction you
            choose to pursue. We may disclose information to comply with law or protect rights,
            safety, and property. We do not sell personal information for money.
          </p>
        </section>

        <section>
          <h2>Cookies and analytics</h2>
          <p>
            We may use cookies or similar technologies to keep the website working, understand
            traffic, remember attribution information, and measure advertising performance. You
            can limit cookies through your browser settings, although parts of the website may not
            function as intended.
          </p>
        </section>

        <section>
          <h2>Data retention and security</h2>
          <p>
            We retain information for as long as reasonably necessary for the purposes described
            here, including maintaining transaction, consent, opt-out, and legal records. We use
            reasonable administrative, technical, and physical safeguards, but no system can
            guarantee absolute security.
          </p>
        </section>

        <section>
          <h2>Your choices</h2>
          <p>
            You may opt out of Stonegate text messages at any time by replying STOP. Reply HELP for
            help. You may also ask us to update your contact preferences or personal information by
            calling <a href="tel:+16785417725">(678) 541-7725</a>. Opting out of texts does not
            prevent you from requesting or accepting a property offer.
          </p>
        </section>

        <section>
          <h2>Children&apos;s privacy</h2>
          <p>
            Our services are intended for adults and are not directed to children under 13. We do
            not knowingly collect personal information from children under 13.
          </p>
        </section>

        <section>
          <h2>Policy updates</h2>
          <p>
            We may update this policy as our practices or legal obligations change. The effective
            date above identifies the latest version.
          </p>
        </section>

        <section>
          <h2>Contact us</h2>
          <p>
            Questions about this policy or our privacy practices may be directed to Stonegate Home
            Buyers by calling <a href="tel:+16785417725">(678) 541-7725</a> or by using our{" "}
            <Link href="/get-a-cash-offer">website contact form</Link>.
          </p>
        </section>
      </article>
      <PublicSiteFooter />
    </main>
  );
}
