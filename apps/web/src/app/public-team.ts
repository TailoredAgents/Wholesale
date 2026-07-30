export type PublicTeamMember = {
  slug: string;
  name: string;
  publicTitle: string;
  biography: string;
  imageSrc: `/images/team/${string}`;
  imageAlt: string;
  featured: boolean;
  organizationFounder: boolean;
  displayOrder: number;
};

// Add a person only after they approve their public name, title, biography, photograph, and alt text.
export const publicTeamMembers: readonly PublicTeamMember[] = [];

const disallowedContent = /\b(?:coming soon|lorem ipsum|placeholder|sample bio|team member)\b/i;

function validatePublicTeamMembers(members: readonly PublicTeamMember[]) {
  const slugs = new Set<string>();
  let featuredCount = 0;
  let founderCount = 0;

  for (const member of members) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(member.slug)) {
      throw new Error(`Public team member slug is invalid: ${member.slug}`);
    }
    if (slugs.has(member.slug)) {
      throw new Error(`Public team member slug is duplicated: ${member.slug}`);
    }
    slugs.add(member.slug);

    if (
      member.name.trim().length < 3 ||
      member.publicTitle.trim().length < 3 ||
      member.biography.trim().length < 80 ||
      member.imageAlt.trim().length < 8
    ) {
      throw new Error(`Public team member content is incomplete: ${member.slug}`);
    }
    if (
      disallowedContent.test(member.name) ||
      disallowedContent.test(member.publicTitle) ||
      disallowedContent.test(member.biography) ||
      disallowedContent.test(member.imageAlt)
    ) {
      throw new Error(`Public team member content contains placeholder language: ${member.slug}`);
    }
    if (!/\.(?:avif|jpe?g|png|webp)$/i.test(member.imageSrc)) {
      throw new Error(`Public team member image format is unsupported: ${member.slug}`);
    }
    if (member.featured) featuredCount += 1;
    if (member.organizationFounder) founderCount += 1;
  }

  if (featuredCount > 1) {
    throw new Error("Only one public team member may be featured on the homepage.");
  }
  if (founderCount > 1) {
    throw new Error("Only one public team member may be identified as the organization founder.");
  }
}

validatePublicTeamMembers(publicTeamMembers);

export function getPublicTeamMembers() {
  return [...publicTeamMembers].sort(
    (left, right) => left.displayOrder - right.displayOrder || left.name.localeCompare(right.name),
  );
}

export function getFeaturedPublicTeamMember() {
  const members = getPublicTeamMembers();
  return members.find((member) => member.featured) ?? members[0] ?? null;
}

export function getPublicOrganizationFounder() {
  return getPublicTeamMembers().find((member) => member.organizationFounder) ?? null;
}
