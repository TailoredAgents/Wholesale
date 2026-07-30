import { ArrowRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { getFeaturedPublicTeamMember, getPublicTeamMembers } from "./public-team";
import styles from "./public-team-identity.module.css";

type PublicTeamIdentityProps = {
  variant: "homepage" | "about";
};

export function PublicTeamIdentity({ variant }: PublicTeamIdentityProps) {
  const members = getPublicTeamMembers();
  if (members.length === 0) return null;

  if (variant === "homepage") {
    const featured = getFeaturedPublicTeamMember();
    if (!featured) return null;

    return (
      <section className={styles.homeSection} data-public-team="true" aria-labelledby="team-title">
        <div className={styles.portrait}>
          <Image
            src={featured.imageSrc}
            alt={featured.imageAlt}
            fill
            quality={78}
            sizes="(max-width: 680px) calc(100vw - 48px), (max-width: 900px) 42vw, 470px"
          />
        </div>
        <div className={styles.homeCopy}>
          <p className={styles.eyebrow}>Meet Stonegate</p>
          <h2 id="team-title">A real person is accountable for your property review.</h2>
          <p className={styles.role}>
            {featured.name} · {featured.publicTitle}
          </p>
          <p className={styles.biography}>{featured.biography}</p>
          <Link className={styles.textLink} href="/about">
            Meet the Stonegate team <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.aboutSection} data-public-team="true" aria-labelledby="about-team-title">
      <div className={styles.sectionHeading}>
        <p className={styles.eyebrow}>The Stonegate team</p>
        <h2 id="about-team-title">The people responsible for your experience.</h2>
        <p>
          Each person shown here is an active part of Stonegate and has approved the information
          published with their photograph.
        </p>
      </div>
      <div className={styles.teamGrid}>
        {members.map((member) => (
          <article className={styles.member} id={member.slug} key={member.slug}>
            <div className={styles.memberPortrait}>
              <Image
                src={member.imageSrc}
                alt={member.imageAlt}
                fill
                quality={78}
                sizes="(max-width: 680px) calc(100vw - 48px), (max-width: 900px) 50vw, 360px"
              />
            </div>
            <div className={styles.memberCopy}>
              <h3>{member.name}</h3>
              <p className={styles.role}>{member.publicTitle}</p>
              <p className={styles.biography}>{member.biography}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
