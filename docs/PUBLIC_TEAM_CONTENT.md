# Stonegate Public Team Content

Last updated: July 30, 2026

## Purpose

This is the approval and handoff guide for publishing real Stonegate team members on the public
website. The homepage and About-page layouts already exist. They intentionally render nothing when
no approved team records exist, so the public site never shows an empty team section, a stock
portrait, an inactive employee, or a “coming soon” biography.

The canonical content file is:

`apps/web/src/app/public-team.ts`

Approved photographs belong in:

`apps/web/public/images/team/`

## Who Should Appear

Publish only active people who regularly participate in the seller experience and who have
approved their public information. The expected initial order is:

1. Founder or owner who is accountable for property review and closing.
2. Active lead or acquisitions contact who may speak with sellers.
3. Active transaction contact who may coordinate paperwork or closing.

Do not publish a planned hire, a temporary contractor, a VA, a private finance role, or a person
who has not agreed to appear. Dispositions personnel should appear only when their public role is
useful and the person has approved it.

## Required Approval Packet

Collect this packet separately for each person:

- exact public name
- exact public title
- an approved biography of two to four sentences
- one approved portrait photograph
- the person's approval to publish the photograph and text
- confirmation that the person is active and should appear now
- preferred display order
- whether the person is the single homepage-featured person
- whether the person is the documented organization founder

The biography should explain what the person actually does for sellers. Do not add licenses,
years of experience, transaction totals, community ties, or professional designations unless the
statement is documented and approved.

## Photograph Standard

Use a recent, truthful photograph of the real person:

- portrait orientation, ideally 4:5
- at least 1200 by 1500 pixels before optimization
- JPG, PNG, WebP, or AVIF
- face and shoulders clearly visible
- sharp focus and even natural light
- simple real background or a genuine Stonegate work setting
- consistent framing, camera height, and lighting across the team
- no text, watermark, artificial backdrop replacement, heavy filter, or AI-generated face

Optional supporting images may show a genuine property visit or natural team interaction. Obtain
permission from every identifiable person and avoid visible seller documents, addresses, license
plates, access codes, or other private information.

Google recommends in-focus, well-lit images that represent reality and specifically recommends
team photographs that humanize the business. Google Search also recommends responsive delivery,
descriptive filenames, and useful alt text.

References:

- `https://support.google.com/business/answer/6123536`
- `https://developers.google.com/search/docs/appearance/google-images`
- `https://www.w3.org/WAI/tutorials/images/informative/`

## File Preparation

1. Keep the untouched original outside the repository.
2. Crop a copy to a 4:5 portrait without cutting through the top of the head or shoulders.
3. Export at approximately 1200 by 1500 pixels.
4. Use a short descriptive filename, for example `austin-founder-closer.webp`.
5. Keep the optimized file under 500 KB when reasonable without visible degradation.
6. Place it in `apps/web/public/images/team/`.
7. Add the approved record to `publicTeamMembers` in `public-team.ts`.

Example structure:

```ts
{
  slug: "approved-public-slug",
  name: "Approved Public Name",
  publicTitle: "Approved Public Title",
  biography: "Approved biography of at least eighty characters that explains the real role.",
  imageSrc: "/images/team/approved-descriptive-photo.webp",
  imageAlt: "Approved Public Name meeting with a property owner in Georgia",
  featured: true,
  organizationFounder: true,
  displayOrder: 10,
}
```

The example is documentation only and is not public content. Do not paste it without replacing
every value with an approved fact.

## Publication Behavior

- No approved records: neither public team section renders.
- One approved record: the person appears on the homepage and About page.
- Multiple approved records: only the single featured person appears on the homepage; all appear
  on the About page in display order.
- No featured record: the first approved person becomes the homepage feature.
- More than one featured record: the build fails.
- Only a person explicitly marked as the organization founder receives founder structured data.
- More than one organization founder: the build fails.
- Incomplete content, unsupported image formats, duplicate slugs, and placeholder language make
  the build fail.

Published people are also added to the homepage Organization structured data as `Person` records.
Homepage prominence and founder identity are separate approvals so a featured salesperson is never
misidentified as the company founder.

## Final Acceptance

After adding the records and images:

1. Run `npm run lint:web`.
2. Run `npm run build:web`.
3. Run the public browser audit at desktop, tablet, and mobile widths.
4. Inspect the homepage and About-page screenshots.
5. Confirm every name, title, biography, and alt description with the person shown.
6. Verify image sharpness and layout stability on a physical phone.
7. Verify the production homepage and About page after deployment.
8. Reuse the approved real photographs in the Stonegate Google Business Profile where appropriate.

Remove a person from `publicTeamMembers` immediately when their public approval is withdrawn or
their role is no longer current. Removing the record removes the person from both pages and
structured data while leaving the source photograph available for a deliberate later cleanup.
