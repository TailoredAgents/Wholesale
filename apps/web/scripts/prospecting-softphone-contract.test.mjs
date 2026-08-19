import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { EventEmitter } from "node:events";
import ts from "typescript";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, "..");
const softphone = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-softphone.ts"),
  "utf8",
);
const dialer = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-dialer.tsx"),
  "utf8",
);
const dialerPolicy = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-dialer-policy.ts"),
  "utf8",
);
const workspace = readFileSync(
  resolve(webRoot, "src/app/os/prospecting/prospecting-workspace.tsx"),
  "utf8",
);
const nextConfig = readFileSync(resolve(webRoot, "next.config.ts"), "utf8");
let softphoneModulePromise;
let dialerPolicyModulePromise;

function importTypeScriptForBehavior(source) {
  const javascript = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`);
}

function importSoftphoneForBehavior() {
  if (!softphoneModulePromise) {
    softphoneModulePromise = importTypeScriptForBehavior(softphone);
  }
  return softphoneModulePromise;
}

function importDialerPolicyForBehavior() {
  if (!dialerPolicyModulePromise) {
    dialerPolicyModulePromise = importTypeScriptForBehavior(dialerPolicy);
  }
  return dialerPolicyModulePromise;
}

test("the prospecting softphone is client-only and lazy-loads the runtime SDK", () => {
  assert.match(softphone, /^"use client";/);
  assert.match(softphone, /import type \{ Call, Device \} from "@twilio\/voice-sdk"/);
  assert.match(softphone, /\(\) => import\("@twilio\/voice-sdk"\)/);
  assert.doesNotMatch(softphone, /import \{ Call, Device \} from "@twilio\/voice-sdk"/);
  assert.doesNotMatch(softphone, /\.register\(/);
});

test("voice tokens stay ephemeral and support proactive refresh", () => {
  assert.match(softphone, /tokenWillExpire/);
  assert.match(softphone, /updateToken\(token\)/);
  assert.doesNotMatch(softphone, /localStorage/);
  assert.doesNotMatch(softphone, /sessionStorage/);
  assert.doesNotMatch(softphone, /console\./);
});

test("microphone denial and temporary audio loss have explicit recovery states", () => {
  assert.match(softphone, /getUserMedia\(\{ audio: true \}\)/);
  assert.match(softphone, /NotAllowedError/);
  assert.match(softphone, /microphone: denied \? "denied" : "error"/);
  assert.match(softphone, /maxCallSignalingTimeoutMs: 30_000/);
  assert.match(softphone, /call\.on\("reconnecting"/);
  assert.match(softphone, /call\.on\("reconnected"/);
});

test("SDK accept is labeled as browser audio and not seller connection", () => {
  assert.match(softphone, /audioLink: "audio_established"/);
  assert.match(softphone, /Browser audio established/);
  assert.match(softphone, /Seller answer and[\s\S]*server-side dial-leg snapshot/);
  assert.doesNotMatch(softphone, /accept[\s\S]{0,120}seller connected/i);
});

test("one browser call is enforced and intent IDs are sent to Twilio", () => {
  assert.match(softphone, /Only one browser call can be active at a time/);
  assert.match(softphone, /params: \{ CallIntentId: callIntentId \}/);
  assert.match(softphone, /closeProtection:/);
});

test("concurrent initialization and connection are single-flight", async () => {
  const { ProspectingSoftphone } = await importSoftphoneForBehavior();
  let deviceCount = 0;
  let microphoneCount = 0;
  let resolveCall;

  class FakeCall extends EventEmitter {
    disconnectCount = 0;
    disconnect() { this.disconnectCount += 1; }
    mute() {}
  }

  class FakeDevice extends EventEmitter {
    static isSupported = true;
    constructor() { super(); deviceCount += 1; }
    connect() { return new Promise((resolve) => { resolveCall = resolve; }); }
    destroy() {}
    updateToken() {}
  }

  const statuses = [];
  const softphone = new ProspectingSoftphone(
    { onStatus: (status) => statuses.push(status), onTokenWillExpire: () => {} },
    {
      loadVoiceSdk: async () => ({ Device: FakeDevice }),
      requestMicrophone: async () => {
        microphoneCount += 1;
        await Promise.resolve();
        return { getTracks: () => [{ stop() {} }] };
      },
    },
  );

  await Promise.all([softphone.initialize("one"), softphone.initialize("two")]);
  assert.equal(deviceCount, 1);
  assert.equal(microphoneCount, 1);

  const firstConnection = softphone.connect("intent-one");
  await assert.rejects(softphone.connect("intent-two"), /Only one browser call/);
  const fakeCall = new FakeCall();
  resolveCall(fakeCall);
  await firstConnection;
  fakeCall.emit("accept");
  await softphone.initialize("refreshed-token");
  assert.equal(statuses.at(-1).audioLink, "audio_established");
});

test("destroying during connection invalidates and disconnects the late call", async () => {
  const { ProspectingSoftphone } = await importSoftphoneForBehavior();
  let resolveCall;
  class FakeCall extends EventEmitter {
    disconnectCount = 0;
    disconnect() { this.disconnectCount += 1; }
    mute() {}
  }
  class FakeDevice extends EventEmitter {
    static isSupported = true;
    connect() { return new Promise((resolve) => { resolveCall = resolve; }); }
    destroy() {}
    updateToken() {}
  }
  const softphone = new ProspectingSoftphone(
    { onStatus: () => {}, onTokenWillExpire: () => {} },
    {
      loadVoiceSdk: async () => ({ Device: FakeDevice }),
      requestMicrophone: async () => ({ getTracks: () => [{ stop() {} }] }),
    },
  );
  await softphone.initialize("token");
  const connection = softphone.connect("intent");
  softphone.destroy();
  const lateCall = new FakeCall();
  resolveCall(lateCall);
  await assert.rejects(connection, /cancelled/);
  assert.equal(lateCall.disconnectCount, 1);
});

test("microphone denial is observable and can be retried without creating a device", async () => {
  const { ProspectingSoftphone } = await importSoftphoneForBehavior();
  let deviceCount = 0;
  class FakeDevice extends EventEmitter {
    static isSupported = true;
    constructor() { super(); deviceCount += 1; }
  }
  const statuses = [];
  const softphone = new ProspectingSoftphone(
    { onStatus: (status) => statuses.push(status), onTokenWillExpire: () => {} },
    {
      loadVoiceSdk: async () => ({ Device: FakeDevice }),
      requestMicrophone: async () => {
        throw new DOMException("blocked", "NotAllowedError");
      },
    },
  );

  await assert.rejects(softphone.initialize("private-token"), /blocked/);
  assert.equal(deviceCount, 0);
  assert.equal(softphone.currentStatus.microphone, "denied");
  assert.equal(softphone.currentStatus.audioLink, "error");
  assert.match(softphone.currentStatus.message, /Allow it in your browser/);
});

test("token refresh and reconnect events preserve an established browser call", async () => {
  const { ProspectingSoftphone } = await importSoftphoneForBehavior();
  const devices = [];
  let tokenExpiryCount = 0;
  class FakeCall extends EventEmitter {
    muted = false;
    disconnect() { this.emit("disconnect"); }
    mute(value) { this.muted = value; this.emit("mute", value); }
  }
  const call = new FakeCall();
  class FakeDevice extends EventEmitter {
    static isSupported = true;
    updatedTokens = [];
    constructor() { super(); devices.push(this); }
    async connect() { return call; }
    destroy() {}
    updateToken(token) { this.updatedTokens.push(token); }
  }
  const statuses = [];
  const softphone = new ProspectingSoftphone(
    {
      onStatus: (status) => statuses.push(status),
      onTokenWillExpire: () => { tokenExpiryCount += 1; },
    },
    {
      loadVoiceSdk: async () => ({ Device: FakeDevice }),
      requestMicrophone: async () => ({ getTracks: () => [{ stop() {} }] }),
    },
  );

  await softphone.initialize("initial-token");
  await softphone.initialize("replacement-token");
  const device = devices[0];
  assert.deepEqual(device.updatedTokens, ["replacement-token"]);
  device.emit("tokenWillExpire");
  await Promise.resolve();
  assert.equal(tokenExpiryCount, 1);

  await softphone.connect("intent-one");
  call.emit("accept");
  call.emit("reconnecting");
  assert.equal(softphone.hasLiveAudio, true);
  assert.equal(softphone.currentStatus.audioLink, "reconnecting");
  call.emit("reconnected");
  assert.equal(softphone.currentStatus.audioLink, "audio_established");
  softphone.setMuted(true);
  assert.equal(statuses.at(-1).muted, true);
  call.emit("disconnect");
  assert.equal(softphone.hasLiveAudio, false);
  assert.equal(softphone.currentStatus.audioLink, "ended");
});

test("dialer feature ownership fails closed until the single-tab controller is ready", async () => {
  const { isNativeDialerFeatureReady, shouldNativeDialerOwnStart } =
    await importDialerPolicyForBehavior();
  const readyContext = {
    feature_enabled: true,
    blockers: [],
    effective_line_cap: 1,
    profile: {
      status: "active",
      user_is_active: true,
      user_calling_enabled: true,
      effective_line_count: 1,
    },
  };
  assert.equal(isNativeDialerFeatureReady(readyContext), true);
  assert.equal(
    isNativeDialerFeatureReady({ ...readyContext, effective_line_cap: 3 }),
    false,
  );
  assert.equal(
    shouldNativeDialerOwnStart({
      context: null,
      leadership: "checking",
      featureReady: false,
      hasSession: false,
      hasLease: false,
    }),
    true,
  );
  assert.equal(
    shouldNativeDialerOwnStart({
      context: { ...readyContext, feature_enabled: false },
      leadership: "leader",
      featureReady: false,
      hasSession: false,
      hasLease: false,
    }),
    false,
  );
  assert.equal(
    shouldNativeDialerOwnStart({
      context: readyContext,
      leadership: "passive",
      featureReady: true,
      hasSession: true,
      hasLease: false,
    }),
    true,
  );
});

test("dialer controls follow durable seller and browser-audio state", async () => {
  const { dialerControlAvailability } = await importDialerPolicyForBehavior();
  const controls = (overrides = {}) =>
    dialerControlAvailability({
      leadership: "leader",
      featureReady: true,
      hasSelectedEntry: true,
      busy: false,
      hasLease: true,
      session: { state: "ready" },
      leg: null,
      voiceCall: null,
      audioLink: "ready",
      ...overrides,
    });

  assert.equal(controls().canStart, true);
  assert.equal(
    controls({
      leg: { status: "queued", call_record_id: "call-one" },
      voiceCall: { provider_call_id: null, leg: { status: "queued" } },
    }).canRetry,
    true,
  );
  assert.equal(
    controls({ leg: { status: "ringing", call_record_id: "call-one" } }).canStopRinging,
    true,
  );
  assert.equal(
    controls({ leg: { status: "connected", call_record_id: "call-one" } }).canHangUp,
    true,
  );
  assert.equal(controls({ session: { state: "paused" } }).canResume, true);
  assert.equal(controls({ session: { state: "reconnecting" } }).canResume, true);
  assert.equal(controls({ audioLink: "reconnecting" }).canMute, true);
  assert.equal(controls({ leadership: "passive" }).canEndShift, false);
});

test("lease recovery replays only the exact pending identity transition", async () => {
  const {
    isPendingLeaseRecoveryForLease,
    shouldDiscardPendingMutation,
    shouldRecoverExpiredLease,
  } =
    await importDialerPolicyForBehavior();
  const lease = { sessionId: "session-one", browserSessionId: "browser-old" };
  const pending = {
    userId: "user-one",
    sessionId: "session-one",
    previousBrowserSessionId: "browser-old",
    newBrowserSessionId: "browser-new",
  };
  assert.equal(isPendingLeaseRecoveryForLease(pending, lease, "user-one"), true);
  assert.equal(isPendingLeaseRecoveryForLease(pending, lease, "other-user"), false);
  assert.equal(
    isPendingLeaseRecoveryForLease(
      { ...pending, previousBrowserSessionId: "different-browser" },
      lease,
      "user-one",
    ),
    false,
  );
  assert.equal(shouldRecoverExpiredLease(409, "Browser lease expired."), true);
  assert.equal(shouldRecoverExpiredLease(409, "Lease belongs to another tab."), false);
  assert.equal(shouldRecoverExpiredLease(500, "Browser lease expired."), false);
  assert.equal(shouldDiscardPendingMutation(422), true);
  assert.equal(shouldDiscardPendingMutation(408), false);
  assert.equal(shouldDiscardPendingMutation(425), false);
  assert.equal(shouldDiscardPendingMutation(429), false);
  assert.equal(shouldDiscardPendingMutation(undefined), false);
});

test("active-call navigation uses a sentinel guard and never auto-dials after reload", () => {
  assert.match(dialer, /sessionStorage/);
  assert.match(dialer, /dialer-start/);
  assert.match(dialer, /dialer-recovery/);
  assert.match(dialer, /history\.pushState\(guardState/);
  assert.match(dialer, /destination\.origin === window\.location\.origin/);
  assert.match(dialer, /window\.confirm\(warning\)/);
  assert.match(dialer, /window\.history\.back\(\)/);
  assert.doesNotMatch(dialer, /window\.history\.forward\(\)/);
  assert.doesNotMatch(dialer, /window\.location\.reload/);
  assert.doesNotMatch(dialer, /localStorage/);
  assert.match(dialer, /Reloading never starts another call automatically/);
  assert.match(dialer, /Dialer control:/);
  assert.match(dialer, /Call status sync:/);
});

test("the workspace sends native lease authority with dispositions", () => {
  assert.match(workspace, /browser_session_id: dialerLease\?\.browserSessionId \?\? null/);
  assert.match(workspace, /lease_token: dialerLease\?\.leaseToken \?\? null/);
  assert.match(workspace, /<ProspectingDialer/);
  assert.match(dialer, /> Start Calling/);
  assert.match(dialer, /> Stop Ringing/);
  assert.match(dialer, /> Hang Up/);
  assert.match(dialer, /> End Shift/);
});

test("production headers permit same-origin microphone access only", () => {
  assert.match(nextConfig, /microphone=\(self\)/);
  assert.doesNotMatch(nextConfig, /microphone=\(\)/);
  for (const deniedCapability of ["camera=()", "geolocation=()", "payment=()", "usb=()"]) {
    assert.match(nextConfig, new RegExp(deniedCapability.replace(/[()]/g, "\\$&")));
  }
});
