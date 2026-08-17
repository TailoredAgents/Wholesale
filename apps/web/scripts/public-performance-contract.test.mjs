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
  const footer = read("src/app/public-site-footer.tsx");
  assert.doesNotMatch(page, /searchParams/);
  assert.match(page, /<PublicSiteHeader variant="conversion" \/>/);
  assert.match(page, /<PublicSiteFooter variant="conversion" \/>/);
  assert.match(form, /window\.location\.search/);
  assert.match(form, /preferredAddress \|\| draft\.values\.property_address/);
  assert.doesNotMatch(form, /name="preferred_contact_method"/);
  assert.match(form, /preferred_contact_method: "phone"/);
  assert.doesNotMatch(form, /Property details may be saved when you continue/);
  assert.match(footer, /!isConversion \? \(\s*<p className=\{styles\.disclosure\}>/);
});

test("standard public pages keep the full navigation shell", () => {
  const homePage = read("src/app/page.tsx");
  assert.match(homePage, /<PublicSiteHeader \/>/);
  assert.match(homePage, /<PublicSiteFooter \/>/);
  assert.doesNotMatch(homePage, /variant="conversion"/);
});

test("cash-offer stages use distinct deduplicated Meta Lead and Contact events", () => {
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  const captureStart = form.indexOf("const captureAddressOnlyLead = useCallback(");
  const captureEnd = form.indexOf("useEffect(() => {", captureStart);
  const captureImplementation = form.slice(captureStart, captureEnd);
  assert.ok(captureStart >= 0 && captureEnd > captureStart);
  assert.match(form, /`stonegate-lead-\$\{intakeAttemptId\}`/);
  assert.match(form, /`stonegate-contact-\$\{intakeAttemptId\}`/);
  assert.match(form, /waitForMetaBrowserCookies\(/);
  assert.match(form, /meta_pixel_event_name\?: "Lead" \| "Contact"/);
  assert.match(form, /const metaPixelEventName = result\.meta_pixel_event_name \?\? "Lead"/);
  assert.match(form, /metaPixelEventName === "Contact"/);
  assert.match(form, /trackMetaPixelEvent\(metaPixelEventName, metaBrowserEvent\.event_id\)/);
  assert.doesNotMatch(form, /pendingMeta(?:Lead|Contact)EventIdRef/);
  assert.ok(
    captureImplementation.indexOf('if (!response?.ok) throw new Error(') <
      captureImplementation.indexOf('addressMetaLeadTrackedRef.current = trackMetaPixelEvent('),
    "The address browser Lead must fire only after the address API confirms success.",
  );
});

test("cash-offer Step 1 saves an idempotent address-only CRM lead without blocking", () => {
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  const captureStart = form.indexOf("const captureAddressOnlyLead = useCallback(");
  const captureEnd = form.indexOf("useEffect(() => {", captureStart);
  const captureImplementation = form.slice(captureStart, captureEnd);
  assert.ok(captureStart >= 0 && captureEnd > captureStart);
  assert.match(form, /stonegate_cash_offer_draft_v1/);
  assert.match(form, /intakeAttemptIdRef/);
  assert.match(form, /intakeAttemptId:\s*intakeAttemptIdRef\.current/);
  assert.match(form, /seller-leads\/address-capture/);
  assert.match(form, /keepalive:\s*true/);
  assert.match(form, /intake_attempt_id:\s*intakeAttemptIdRef\.current/);
  assert.match(form, /void captureAddressOnlyLead\(values\)/);
  assert.ok(
    form.indexOf("void captureAddressOnlyLead(values)") <
      form.indexOf("moveToStep(Math.min(activeStep + 1"),
    "Address capture should start before Step 2 while navigation remains nonblocking.",
  );
  assert.ok(
    captureImplementation.indexOf("sendAddressCapture(initialMetaBrowserEvent)") <
      captureImplementation.indexOf("waitForMetaBrowserCookies("),
    "The first persistence request must start before Meta cookie polling begins.",
  );
  assert.ok(
    captureImplementation.indexOf("await initialAddressCaptureRequest") <
      captureImplementation.indexOf("await strongestMetaBrowserEventPromise"),
    "The first persistence request must start before waiting for Meta browser cookies.",
  );
  assert.match(form, /confirmedAddressCaptureSignatureRef/);
  assert.match(form, /addressCaptureInFlightRef/);
  assert.match(form, /retryIfInFlight:\s*true/);
  assert.match(form, /retryWithEnrichedCookies:\s*false/);
  assert.doesNotMatch(
    captureImplementation,
    /desired_timeline/,
    "Step 1 must persist only the property address, without requiring seller timing.",
  );
  assert.match(form, /window\.addEventListener\("pagehide", handlePageExit\)/);
  assert.match(form, /window\.addEventListener\("beforeunload", handlePageExit\)/);
  assert.match(form, /document\.addEventListener\("visibilitychange", handleVisibilityChange\)/);
  assert.doesNotMatch(form, /formPrivacy|Property details may be saved when you continue/);
});

test("cash-offer seller timeline is optional post-submit enrichment", () => {
  const form = read("src/app/get-a-cash-offer/cash-offer-form.tsx");
  const enrichmentStart = form.indexOf("async function handleEnrichmentSubmit(");
  const enrichmentEnd = form.indexOf("function startAnotherProperty()", enrichmentStart);
  const enrichmentImplementation = form.slice(enrichmentStart, enrichmentEnd);
  const stepOneStart = form.indexOf("{activeStep === 0 ? (");
  const stepOneEnd = form.indexOf("{activeStep === 1 ? (", stepOneStart);
  const stepOneMarkup = form.slice(stepOneStart, stepOneEnd);

  assert.ok(enrichmentStart >= 0 && enrichmentEnd > enrichmentStart);
  assert.ok(stepOneStart >= 0 && stepOneEnd > stepOneStart);
  assert.doesNotMatch(stepOneMarkup, /desired_timeline/);
  assert.match(enrichmentImplementation, /desired_timeline:\s*values\.desired_timeline \|\| null/);
  assert.match(form, /label="When might you ideally like to sell\?"/);
  assert.match(form, /name="desired_timeline" hint="Optional"/);
  assert.doesNotMatch(form, /name="desired_timeline"[^>]*required/);
});

test("the public Meta bootstrap runs before hydration and shares route state", () => {
  const layout = read("src/app/layout.tsx");
  const bootstrap = read("src/app/lib/meta-pixel-bootstrap.ts");
  const conversions = read("src/app/lib/conversion-events.ts");
  assert.match(layout, /strategy="beforeInteractive"/);
  assert.match(layout, /buildMetaPixelBootstrap/);
  assert.match(bootstrap, /nonPublicTrackingRoutePrefixes/);
  assert.match(bootstrap, /__stonegateMetaLastPageViewPath/);
  assert.match(bootstrap, /q\("track","PageView"\)/);
  assert.match(conversions, /window\.__stonegateMetaLastPageViewPath/);
});

test("public conversion tracking follows route and event identity", () => {
  const tracker = read("src/app/public-conversion-tracker.tsx");
  assert.match(tracker, /usePathname\(\)/);
  assert.match(tracker, /lastRecordedIdentity/);
  assert.match(tracker, /metadataIdentity/);
  assert.doesNotMatch(tracker, /hasRecorded/);
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
