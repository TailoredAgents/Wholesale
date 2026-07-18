import type { Metadata } from "next";
import Link from "next/link";

import styles from "../legal-page.module.css";
import { PublicSiteFooter } from "../public-site-footer";

export const metadata: Metadata = {
  title: "Terms & Conditions | Stonegate Home Buyers",
  description: "Website and SMS terms for Stonegate Home Buyers.",
};

export default function TermsPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          Stonegate Home Buyers
        </Link>
        <nav aria-label="Primary navigation">
          <Link href="/get-a-cash-offer">Get a cash offer</Link>
          <Link href="/privacy-policy">Privacy Policy</Link>
        </nav>
      </header>

      <article className={styles.content}>
        <p className={styles.eyebrow}>Stonegate Home Buyers</p>
        <h1>Terms &amp; Conditions</h1>
        <p className={styles.effective}>Effective July 18, 2026</p>
        <p className={styles.intro}>
          These Terms &amp; Conditions govern your use of the Stonegate Home Buyers website,
          property inquiry services, and text-messaging program.
        </p>

        <section>
          <h2>Website use</h2>
          <p>
            You may use this website to learn about Stonegate Home Buyers and submit accurate
            information about a property you own or are authorized to discuss. You may not misuse
            the website, interfere with its operation, submit fraudulent information, or attempt
            unauthorized access to our systems.
          </p>
        </section>

        <section>
          <h2>Property inquiries and offers</h2>
          <p>
            Submitting a property inquiry does not create a purchase agreement, agency
            relationship, appraisal, or guarantee of an offer. Any potential offer is subject to
            property review, title and ownership verification, inspection or access when
            applicable, and written agreement signed by the relevant parties. You are free to
            decline an offer and seek independent legal, tax, financial, or real-estate advice.
          </p>
        </section>

        <section className={styles.smsNotice}>
          <h2>Stonegate Home Buyers SMS program</h2>
          <p>
            When you separately check the SMS consent box on our cash-offer form, you agree to
            receive recurring automated text messages from Stonegate Home Buyers about your
            property inquiry, qualification questions, appointments, cash-offer updates, and
            related follow-up. Message frequency varies based on your inquiry and interactions.
            Message and data rates may apply. Consent to receive text messages is not a condition
            of purchasing or selling property or receiving an offer.
          </p>
        </section>

        <section>
          <h2>Opting out and getting help</h2>
          <p>
            Reply STOP to any Stonegate Home Buyers text message to unsubscribe. You may receive one
            final confirmation that your opt-out was processed. After opting out, no additional
            program messages will be sent unless you provide new consent. Reply HELP for help or
            call <a href="tel:+16785417725">(678) 541-7725</a>. Carriers are not liable for delayed
            or undelivered messages.
          </p>
        </section>

        <section>
          <h2>Message delivery</h2>
          <p>
            Text-message delivery is subject to your wireless carrier and network availability.
            Stonegate Home Buyers does not guarantee that every message will be delivered or
            received at a particular time. You are responsible for charges imposed by your carrier.
            Keep your phone number current and do not provide a number you are not authorized to
            use.
          </p>
        </section>

        <section>
          <h2>Privacy</h2>
          <p>
            Our <Link href="/privacy-policy">Privacy Policy</Link> explains how we collect and use
            information. Mobile phone information, text-message opt-in data, and consent are not
            sold or shared with third parties or affiliates for their own marketing or promotional
            purposes.
          </p>
        </section>

        <section>
          <h2>Third-party services and links</h2>
          <p>
            The website may rely on or link to third-party services. Stonegate Home Buyers is not
            responsible for third-party websites, terms, availability, or privacy practices.
          </p>
        </section>

        <section>
          <h2>Disclaimer and limitation</h2>
          <p>
            The website is provided on an as-available basis. To the extent permitted by law,
            Stonegate Home Buyers disclaims implied warranties and is not liable for indirect,
            incidental, special, or consequential damages arising from website use. These terms do
            not limit rights or remedies that cannot legally be limited.
          </p>
        </section>

        <section>
          <h2>Changes to these terms</h2>
          <p>
            We may update these terms as our services or legal obligations change. The effective
            date above identifies the latest version. Continued use of the website after an update
            means the updated terms apply to future use.
          </p>
        </section>

        <section>
          <h2>Contact us</h2>
          <p>
            Questions about these terms or the Stonegate Home Buyers messaging program may be
            directed to <a href="tel:+16785417725">(678) 541-7725</a> or submitted through our{" "}
            <Link href="/get-a-cash-offer">website contact form</Link>.
          </p>
        </section>
      </article>
      <PublicSiteFooter />
    </main>
  );
}
