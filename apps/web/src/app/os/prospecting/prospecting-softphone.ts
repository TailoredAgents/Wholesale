"use client";

import {
  WebPhoneRuntime,
  type WebPhoneAudioLinkState,
  type WebPhoneMicrophoneState,
  type WebPhoneStatus,
} from "../_components/web-phone-runtime";

/**
 * Backwards-compatible prospecting names for the shared Stonegate web phone.
 * Prospecting retains its own dial-session coordinator and server-side truth;
 * only the browser headset runtime is shared with Inbox and Dispositions.
 */
export type ProspectingAudioLinkState = WebPhoneAudioLinkState;
export type ProspectingMicrophoneState = WebPhoneMicrophoneState;
export type ProspectingSoftphoneStatus = WebPhoneStatus;

export class ProspectingSoftphone extends WebPhoneRuntime {}
