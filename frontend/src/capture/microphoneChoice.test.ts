import { describe, expect, it } from "vitest";
import { chooseMicrophone, isIphoneMicrophone, microphoneOptions, type Microphone } from "./microphoneChoice";

// Shapes as Chrome on macOS exposes them once the site holds microphone permission: CoreAudio names
// plus a transport suffix, and a "default" alias labelled "Default - <device>" sharing that device's
// group id (measured, Chrome 154). A Continuity iPhone has no suffix.
const input = (deviceId: string, label: string, groupId = `g-${deviceId}`): Microphone =>
  ({ kind: "audioinput", deviceId, groupId, label });
const defaultIs = (device: Microphone): Microphone =>
  input("default", `Default - ${device.label}`, device.groupId);

const iphone = input("phone", "Gao’s iPhone Microphone");
const builtIn = input("builtin", "MacBook Pro Microphone (Built-in)");
const blackHole = input("blackhole", "BlackHole 2ch (Virtual)");
const airPods = input("airpods", "AirPods (Bluetooth)");
const headsetJack = input("jack", "External Microphone (Built-in)");
const usbHeadset = input("usb", "Jabra Evolve2 65 (0b0e:24c1)");

describe("microphone choice (issue #2)", () => {
  it("skips an iPhone system default for the built-in microphone, not the loopback listed first", () => {
    const devices = [defaultIs(iphone), blackHole, iphone, builtIn];
    expect(chooseMicrophone(devices)).toBe("builtin");
  });

  it("prefers connected headphones over the built-in microphone when the default is an iPhone", () => {
    expect(chooseMicrophone([defaultIs(iphone), builtIn, iphone, airPods])).toBe("airpods");
    expect(chooseMicrophone([defaultIs(iphone), builtIn, iphone, headsetJack])).toBe("jack");
    expect(chooseMicrophone([defaultIs(iphone), builtIn, usbHeadset, iphone])).toBe("usb");
  });

  it("uses a system default that is not an iPhone as it is", () => {
    expect(chooseMicrophone([defaultIs(airPods), builtIn, airPods, iphone])).toBe("airpods");
    // The person's machine chose the built-in microphone; a connected headset does not override it.
    expect(chooseMicrophone([defaultIs(builtIn), builtIn, airPods, iphone])).toBe("builtin");
  });

  it("honours an explicit iPhone pick, and falls back to the rule when a pick is unplugged", () => {
    expect(chooseMicrophone([defaultIs(builtIn), builtIn, iphone], "phone")).toBe("phone");
    expect(chooseMicrophone([defaultIs(builtIn), builtIn], "airpods")).toBe("builtin");
  });

  it("keeps the open microphone when an iPhone becomes the default", () => {
    expect(chooseMicrophone([defaultIs(iphone), builtIn, iphone, airPods], "", "builtin")).toBe("builtin");
    // An open iPhone is not kept on its own account.
    expect(chooseMicrophone([defaultIs(iphone), builtIn, iphone], "", "phone")).toBe("builtin");
  });

  it("opens an iPhone that is the only microphone", () => {
    expect(chooseMicrophone([defaultIs(iphone), iphone])).toBe("phone");
  });

  it("offers nothing and chooses nothing while Chrome hides the devices", () => {
    // Before permission Chrome exposes one audio input with empty id, group and label (measured).
    const hidden = [{ kind: "audioinput", deviceId: "", groupId: "", label: "" } as Microphone];
    expect(microphoneOptions(hidden)).toEqual([]);
    expect(chooseMicrophone(hidden)).toBeNull();
  });

  it("lists each microphone once under its own name", () => {
    const camera: Microphone = { ...input("cam", "FaceTime HD Camera"), kind: "videoinput" };
    expect(microphoneOptions([defaultIs(iphone), iphone, builtIn, camera])).toEqual([iphone, builtIn]);
    // An alias Chrome cannot tie to a device stands for the default itself.
    const bare = input("default", "Default", "");
    expect(microphoneOptions([bare, builtIn])).toEqual([bare, builtIn]);
    expect(chooseMicrophone([bare, builtIn])).toBe("default");
  });

  it("recognises Continuity microphones by the phone's name", () => {
    expect(isIphoneMicrophone(iphone)).toBe(true);
    expect(isIphoneMicrophone({ label: "iPhone Microphone" })).toBe(true);
    expect(isIphoneMicrophone(defaultIs(iphone))).toBe(true);
    expect(isIphoneMicrophone(builtIn)).toBe(false);
    expect(isIphoneMicrophone(airPods)).toBe(false);
  });
});
