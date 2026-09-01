import type { Metadata } from "next";
import {
  ArrowRight,
  Check,
  Clock3,
  House,
  Mail,
  MapPin,
  Phone,
} from "lucide-react";
import Link from "next/link";

import { PublicConversionTracker } from "../public-conversion-tracker";
import { PublicSiteFooter } from "../public-site-footer";
import { PublicSiteHeader } from "../public-site-header";
import { directOfferDisclosure, siteConfig } from "../site-config";
import { TrackedEmailLink } from "../tracked-email-link";
import { TrackedPhoneLink } from "../tracked-phone-link";
import contentStyles from "../public-content.module.css";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Contact Stonegate Home Buyers | Metro Atlanta Service Area",
  description:
    "Contact Stonegate Home Buyers about a Georgia property and learn how we confirm service coverage in metro Atlanta and surrounding communities.",
  alternates: { canonical: "/contact" },
};

const expectations = [
  {
    title: "Start with the property",
    detail: "An address lets the team confirm location and prepare the first review.",
  },
  {
    title: "Know what happens next",
    detail:
      "Stonegate may follow up by phone, email, or a one-to-one text about your inquiry. Recurring automated texts require separate optional SMS consent.",
  },
  {
    title: "Confirm coverage first",
    detail: "Stonegate confirms that the property is in an area the team can responsibly evaluate.",
  },
];

export default function ContactPage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "ContactPage",
    name: `Contact ${siteConfig.name}`,
    url: `${siteConfig.siteUrl}/contact`,
    mainEntity: {
      "@type": "Organization",
      "@id": `${siteConfig.siteUrl}/#organization`,
      name: siteConfig.name,
      url: siteConfig.siteUrl,
      email: siteConfig.publicEmail,
      telephone: siteConfig.phoneE164,
      areaServed: [
        { "@type": "State", name: "Georgia" },
        { "@type": "Place", name: "Metro Atlanta, Georgia" },
      ],
      contactPoint: {
        "@type": "ContactPoint",
        contactType: "seller inquiries",
        email: siteConfig.publicEmail,
        telephone: siteConfig.phoneE164,
        areaServed: "US-GA",
        availableLanguage: "English",
      },
    },
  };

  return (
    <main className={contentStyles.page}>
      <PublicConversionTracker metadata={{ page: "contact" }} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <PublicSiteHeader />

      <section className={contentStyles.hero}>
        <p className={contentStyles.eyebrow}>Contact and service area</p>
        <h1>Talk with Stonegate about a Georgia property.</h1>
        <p>
          Start with the address or contact the team directly. We confirm local coverage before
          asking you to schedule a property visit or rely on an offer.
        </p>
        <div className={contentStyles.heroActions}>
          <TrackedPhoneLink
            className={contentStyles.primaryAction}
            href={siteConfig.phoneHref}
            metadata={{ placement: "contact_hero" }}
          >
            <Phone size={17} aria-hidden="true" />
            {siteConfig.phoneDisplay}
          </TrackedPhoneLink>
          <TrackedEmailLink
            className={contentStyles.secondaryAction}
            href={`${siteConfig.publicEmailHref}?subject=Property%20inquiry`}
            metadata={{ placement: "contact_hero" }}
          >
            <Mail size={17} aria-hidden="true" />
            Email Stonegate
          </TrackedEmailLink>
        </div>
      </section>

      <section className={styles.contactSection} aria-labelledby="contact-options-title">
        <div>
          <p className={contentStyles.eyebrow}>Seller inquiries</p>
          <h2 id="contact-options-title">Use the contact method that works for you.</h2>
          <p>
            A property request creates the clearest record for follow-up. Calling or emailing is
            also available when you want to speak first.
          </p>
        </div>
        <div className={styles.contactMethods}>
          <TrackedPhoneLink
            className={styles.contactMethod}
            href={siteConfig.phoneHref}
            metadata={{ placement: "contact_details" }}
          >
            <Phone size={21} aria-hidden="true" />
            <span>
              <small>Call Stonegate</small>
              <strong>{siteConfig.phoneDisplay}</strong>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </TrackedPhoneLink>
          <TrackedEmailLink
            className={styles.contactMethod}
            href={`${siteConfig.publicEmailHref}?subject=Property%20inquiry`}
            metadata={{ placement: "contact_details" }}
          >
            <Mail size={21} aria-hidden="true" />
            <span>
              <small>Email seller inquiries</small>
              <strong>{siteConfig.publicEmail}</strong>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </TrackedEmailLink>
          <div className={styles.availability}>
            <Clock3 size={21} aria-hidden="true" />
            <span>
              <small>Request availability</small>
              <strong>{siteConfig.inquiryAvailability}</strong>
              <em>A team member follows up about the property inquiry.</em>
            </span>
          </div>
        </div>
      </section>

      <section className={contentStyles.darkBand}>
        <div>
          <p className={contentStyles.eyebrow}>Initial service area</p>
          <h2>{siteConfig.serviceAreaShort}</h2>
        </div>
        <div>
          <p>
            Stonegate is beginning in Georgia with an initial focus on metro Atlanta. Coverage can
            vary by property location and current team capacity, so the address is always confirmed
            before the process moves forward.
          </p>
          <p>
            Outside the immediate area? You can still submit the property. We will tell you whether
            Stonegate can evaluate it instead of implying coverage we have not confirmed.
          </p>
          <Link className={contentStyles.bandLink} href="/service-areas/metro-atlanta">
            See how Metro Atlanta coverage works <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className={styles.expectationSection}>
        <div className={styles.expectationHeading}>
          <p className={contentStyles.eyebrow}>What happens next</p>
          <h2>A direct and documented handoff.</h2>
        </div>
        <div className={styles.expectations}>
          {expectations.map((expectation) => (
            <div key={expectation.title}>
              <Check size={18} aria-hidden="true" />
              <span>
                <strong>{expectation.title}</strong>
                {expectation.detail}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.visitSection}>
        <div>
          <MapPin size={24} aria-hidden="true" />
          <span>
            <p className={contentStyles.eyebrow}>Property meetings</p>
            <h2>When an in-person review helps, we meet at the property by appointment.</h2>
          </span>
        </div>
        <div>
          <House size={22} aria-hidden="true" />
          <p>
            The seller process starts by phone, email, or the property-request form. A Stonegate
            team member confirms the next step before anyone arrives at the house.
          </p>
        </div>
      </section>

      <section className={contentStyles.finalCta}>
        <div>
          <p className={contentStyles.eyebrow}>Ready to start?</p>
          <h2>Share the address without committing to sell.</h2>
        </div>
        <Link className={contentStyles.primaryAction} href="/get-a-cash-offer">
          Request a Property Review <ArrowRight size={17} aria-hidden="true" />
        </Link>
      </section>
      <p className={contentStyles.disclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
