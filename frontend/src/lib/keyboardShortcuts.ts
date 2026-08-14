type ShortcutKeyEvent = Pick<
  KeyboardEvent,
  "altKey" | "ctrlKey" | "key" | "metaKey" | "shiftKey"
>;

export function isApplePlatform(platform = readNavigatorPlatform()): boolean {
  const normalizedPlatform = platform.trim().toLowerCase();
  return (
    normalizedPlatform.includes("mac") ||
    normalizedPlatform.includes("iphone") ||
    normalizedPlatform.includes("ipad") ||
    normalizedPlatform.includes("ipod")
  );
}

export function matchesPrimaryShortcut(
  event: ShortcutKeyEvent,
  key: string,
  platform = readNavigatorPlatform()
): boolean {
  if (event.altKey || event.shiftKey || event.key.toLowerCase() !== key.toLowerCase()) {
    return false;
  }

  return isApplePlatform(platform)
    ? Boolean(event.metaKey) && !event.ctrlKey
    : Boolean(event.ctrlKey) && !event.metaKey;
}

function readNavigatorPlatform(): string {
  return typeof navigator === "undefined" ? "" : navigator.platform ?? "";
}
