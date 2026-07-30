import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ServiceAreaPage } from "../../service-area-page";
import { findServiceArea, serviceAreas } from "../../service-areas";
import { siteConfig } from "../../site-config";

type PageProps = {
  params: Promise<{ slug: string }>;
};

export function generateStaticParams() {
  return serviceAreas.map((area) => ({ slug: area.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const area = findServiceArea(slug);

  if (!area) {
    return {};
  }

  return {
    title: `${area.name} Home Buyers | Sell Your House As-Is`,
    description: area.description,
    alternates: { canonical: `/service-areas/${area.slug}` },
    openGraph: {
      type: "website",
      url: `${siteConfig.siteUrl}/service-areas/${area.slug}`,
      title: `${area.name} Home Buyers | ${siteConfig.name}`,
      description: area.description,
      images: [{ url: area.image, alt: area.imageAlt }],
    },
  };
}

export default async function ServiceAreaRoute({ params }: PageProps) {
  const { slug } = await params;
  const area = findServiceArea(slug);

  if (!area) {
    notFound();
  }

  return <ServiceAreaPage area={area} />;
}
