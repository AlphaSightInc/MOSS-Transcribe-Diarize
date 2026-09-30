/**
 * Which microphone opens when the person has not picked one (issue #2).
 *
 * The rule: the operating system's default input, unless that is an iPhone reached through
 * Continuity. Then the microphone already open stays; failing that, the best other microphone.
 * An iPhone opens only when the person picks it, or when it is the only microphone there is.
 *
 * The page opens the device this names by exact id and never lets Chrome choose. A request
 * without a device id is resolved by Chrome's own per-profile device ranking rather than the
 * system default, and makes Chrome on macOS probe every input, which wakes a nearby iPhone.
 * Evidence and limits: `docs/design-capture-setup.md` (Microphone choice).
 */

/** Chrome's alias for the operating system's default input. */
export const DEFAULT_MICROPHONE_ID = "default";

export type Microphone = Pick<MediaDeviceInfo, "deviceId" | "groupId" | "kind" | "label">;

/**
 * macOS names a Continuity microphone after the phone ("Gao’s iPhone Microphone"), and Chrome
 * adds no transport suffix to it. A phone renamed without the word "iPhone" is not recognised.
 */
export function isIphoneMicrophone(microphone: Pick<Microphone, "label">): boolean {
  return /\biPhone\b/i.test(microphone.label);
}

/**
 * The microphones a person can pick, in Chrome's order. Chrome's default alias is folded into
 * the device it stands for, so each microphone is listed once under its own name. Empty until
 * the site holds microphone permission: until then Chrome hides every device id and label.
 */
export function microphoneOptions(devices: readonly Microphone[]): Microphone[] {
  const inputs = labelledInputs(devices);
  const byDefault = systemDefault(inputs);
  return byDefault && byDefault.deviceId !== DEFAULT_MICROPHONE_ID
    ? inputs.filter(device => device.deviceId !== DEFAULT_MICROPHONE_ID) : inputs;
}

/**
 * The device id to open: the person's pick if it is present, else the automatic rule above.
 * `open` is the microphone already running, which an iPhone becoming the default never displaces.
 * Null while Chrome hides the devices.
 */
export function chooseMicrophone(devices: readonly Microphone[], picked = "", open = ""): string | null {
  const inputs = labelledInputs(devices);
  const options = microphoneOptions(inputs);
  const present = (id: string) => options.find(device => device.deviceId === id);
  const byPick = present(picked);
  if (byPick) return byPick.deviceId;
  const byDefault = systemDefault(inputs);
  if (byDefault && !isIphoneMicrophone(byDefault)) return byDefault.deviceId;
  const running = present(open);
  if (running && !isIphoneMicrophone(running)) return running.deviceId;
  const best = options.filter(device => !isIphoneMicrophone(device))
    .reduce<Microphone | undefined>((found, device) => !found || rank(device) < rank(found) ? device : found, undefined);
  return (best ?? byDefault ?? options[0])?.deviceId ?? null;
}

/**
 * The concrete device behind Chrome's default alias. Chrome labels the alias
 * "Default - <that device's label>" and gives it that device's group id (measured, Chrome 154
 * on macOS). Without a match the alias itself stands for the default.
 */
function systemDefault(inputs: readonly Microphone[]): Microphone | undefined {
  const alias = inputs.find(device => device.deviceId === DEFAULT_MICROPHONE_ID);
  if (!alias) return undefined;
  return inputs.find(device => device !== alias && device.groupId === alias.groupId &&
    alias.label.endsWith(` - ${device.label}`)) ?? alias;
}

function labelledInputs(devices: readonly Microphone[]): Microphone[] {
  return devices.filter(device => device.kind === "audioinput" && device.deviceId && device.label);
}

/**
 * Preference among the other microphones, read from the transport suffix Chrome on macOS puts on
 * every label: a headset or external microphone first (Bluetooth, USB "(vid:pid)", or the
 * headset jack's "External Microphone"), then the built-in one, then the rest -- virtual
 * loopbacks such as BlackHole carry no voice.
 */
function rank(microphone: Microphone): number {
  if (/\((?:Bluetooth(?: LE)?|[0-9a-f]{4}:[0-9a-f]{4})\)$/i.test(microphone.label) ||
      /^External\b/i.test(microphone.label)) return 0;
  if (/\(Built-in\)$/i.test(microphone.label)) return 1;
  return 2;
}
