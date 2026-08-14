import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const root = process.cwd();
const read = (path) => readFileSync(join(root, path), "utf8");

test("public routes do not load the staff authentication provider", () => {
  const rootLayout = read("src/app/layout.tsx");
  assert.doesNotMatch(rootLayout, /ClerkProvider/);

  for (const path of [
    "src/app/os/layout.tsx",
    "src/app/leads/layout.tsx",
    "src/app/sign-in/layout.tsx",
    "src/app/sign-up/layout.tsx",
  ]) {
    assert.match(read(path), /ClerkProvider/);
  }
});

test("Clerk middleware runs only for authentication and protected workspaces", () => {
  const proxy = read("src/proxy.ts");
  assert.doesNotMatch(proxy, /\(\?!_next/);
  for (const route of ["/os/:path*", "/leads/:path*", "/sign-in/:path*", "/sign-up/:path*"]) {
    assert.match(proxy, new RegExp(route.replace(/[/*]/g, "\\$&")));
  }
});

test("cash-offer page stays static while preserving address-query restoration", () => {
  const page = read("src/app/get-a-cash-offer/page.tsx");
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  assert.doesNotMatch(page, /searchParams/);
  assert.match(page, /<PublicSiteHeader variant="conversion" \/>/);
  assert.match(page, /<PublicSiteFooter variant="conversion" \/>/);
  assert.match(form, /window\.location\.search/);
  assert.match(form, /preferredAddress \|\| draft\.values\.property_address/);
  assert.doesNotMatch(form, /name="preferred_contact_method"/);
  assert.match(form, /preferred_contact_method: "phone"/);
});

test("standard public pages keep the full navigation shell", () => {
  const homePage = read("src/app/page.tsx");
  assert.match(homePage, /<PublicSiteHeader \/>/);
  assert.match(homePage, /<PublicSiteFooter \/>/);
  assert.doesNotMatch(homePage, /variant="conversion"/);
});

test("successful cash-offer submissions report one deduplicated Meta Lead", () => {
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  assert.match(
    form,
    /trackMetaPixelEvent\("Lead", metaBrowserEvent\.event_id\)/,
  );
  assert.doesNotMatch(
    form,
    /trackMetaPixelEvent\("Contact", metaBrowserEvent\.event_id\)/,
  );
});

test("seller intake does not wait on optional experiment tracking", () => {
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  const conversions = read("src/app/lib/conversion-events.ts");
  assert.doesNotMatch(form, /await getConversionExperimentContext\(apiBaseUrl\)/);
  assert.match(form, /experimentContextRef\.current/);
  assert.doesNotMatch(form, /getStoredConversionExperimentContext\(\)/);
  assert.match(conversions, /experimentRequestTimeoutMs/);
  assert.doesNotMatch(conversions, /latestStoredExperiment/);
});

test("cash-offer address autocomplete remains optional and mobile-first", () => {
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  const address = read("src/app/get-a-cash-offer/property-address-field.tsx");
  const page = read("src/app/get-a-cash-offer/page.tsx");
  const styles = read("src/app/get-a-cash-offer/page.module.css");
  assert.match(form, /<PropertyAddressField/);
  assert.match(address, /\/api\/v1\/public\/address-suggestions/);
  assert.match(address, /Enter address manually/);
  assert.match(address, /role="combobox"/);
  assert.match(address, /role="listbox"/);
  assert.match(address, /activeIndex >= 0 \? activeIndex : 0/);
  assert.match(address, /styles\.manualAddressCollapsed/);
  assert.match(address, /onPointerDownCapture/);
  assert.match(page, /className={styles\.leftRail}/);
  assert.match(styles, /\.leftRail\s*{[^}]*display:\s*contents;/s);
  assert.match(styles, /\.form,\s*\.confirmation\s*{[^}]*order:\s*2;/s);
});

test("public images expose right-sized responsive candidates", () => {
  assert.match(read("src/app/stonegate-logo.tsx"), /sizes="44px"/);
  const nextConfig = read("next.config.ts");
  assert.match(nextConfig, /deviceSizes: \[[^\]]*1440[^\]]*1600/);
  assert.match(nextConfig, /imageSizes: \[[^\]]*512/);
});
