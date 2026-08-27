import AppKit
import ApplicationServices
import Foundation

struct Record: Codable {
    let path: String
    let role: String
    let title: String?
    let value: String?
    let description: String?
    let x: Double?
    let y: Double?
    let width: Double?
    let height: Double?
    let actions: [String]
}

func attribute(_ element: AXUIElement, _ name: CFString) -> AnyObject? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name, &value) == .success else { return nil }
    return value as AnyObject?
}

func stringAttribute(_ element: AXUIElement, _ name: CFString) -> String? {
    attribute(element, name) as? String
}

func pointAttribute(_ element: AXUIElement, _ name: CFString) -> CGPoint? {
    guard let value = attribute(element, name), CFGetTypeID(value) == AXValueGetTypeID() else { return nil }
    var point = CGPoint.zero
    guard AXValueGetValue(value as! AXValue, .cgPoint, &point) else { return nil }
    return point
}

func sizeAttribute(_ element: AXUIElement, _ name: CFString) -> CGSize? {
    guard let value = attribute(element, name), CFGetTypeID(value) == AXValueGetTypeID() else { return nil }
    var size = CGSize.zero
    guard AXValueGetValue(value as! AXValue, .cgSize, &size) else { return nil }
    return size
}

func childElements(_ element: AXUIElement) -> [AXUIElement] {
    (attribute(element, kAXChildrenAttribute as CFString) as? [AXUIElement]) ?? []
}

func actionNames(_ element: AXUIElement) -> [String] {
    var names: CFArray?
    guard AXUIElementCopyActionNames(element, &names) == .success else { return [] }
    return (names as? [String]) ?? []
}

func walk(_ element: AXUIElement, path: String, depth: Int, seen: inout Set<CFHashCode>, records: inout [Record]) {
    guard depth < 40 else { return }
    let identity = CFHash(element)
    guard seen.insert(identity).inserted else { return }
    let role = stringAttribute(element, kAXRoleAttribute as CFString) ?? ""
    if role == kAXStaticTextRole as String || role == kAXButtonRole as String || role == kAXScrollAreaRole as String {
        let position = pointAttribute(element, kAXPositionAttribute as CFString)
        let size = sizeAttribute(element, kAXSizeAttribute as CFString)
        records.append(Record(
            path: path,
            role: role,
            title: stringAttribute(element, kAXTitleAttribute as CFString),
            value: stringAttribute(element, kAXValueAttribute as CFString),
            description: stringAttribute(element, kAXDescriptionAttribute as CFString),
            x: position.map { Double($0.x) }, y: position.map { Double($0.y) },
            width: size.map { Double($0.width) }, height: size.map { Double($0.height) },
            actions: actionNames(element)
        ))
    }
    for (index, child) in childElements(element).enumerated() {
        walk(child, path: "\(path)/\(index)", depth: depth + 1, seen: &seen, records: &records)
    }
}

guard CommandLine.arguments.count >= 2 else {
    fputs("usage: projectclerk_ax <snapshot|scroll|click-button> [arguments]\n", stderr)
    exit(2)
}
guard AXIsProcessTrusted() else {
    fputs("Accessibility permission is not granted\n", stderr)
    exit(3)
}
guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: "com.projectclerk.app").first else {
    fputs("ProjectClerk is not running\n", stderr)
    exit(4)
}

switch CommandLine.arguments[1] {
case "snapshot":
    let root = AXUIElementCreateApplication(app.processIdentifier)
    var records: [Record] = []
    var seen = Set<CFHashCode>()
    walk(root, path: "root", depth: 0, seen: &seen, records: &records)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(records))
    FileHandle.standardOutput.write(Data("\n".utf8))
case "scroll":
    let delta = Int32(CommandLine.arguments.count >= 3 ? (Int(CommandLine.arguments[2]) ?? 0) : 0)
    app.activate(options: [.activateIgnoringOtherApps])
    let root = AXUIElementCreateApplication(app.processIdentifier)
    var records: [Record] = []
    var seen = Set<CFHashCode>()
    walk(root, path: "root", depth: 0, seen: &seen, records: &records)
    let target = records
        .filter { $0.role == kAXScrollAreaRole as String && ($0.width ?? 0) >= 400 }
        .max { ($0.width ?? 0) * ($0.height ?? 0) < ($1.width ?? 0) * ($1.height ?? 0) }
    guard let target else { exit(5) }
    func findScrollTarget(_ element: AXUIElement, path: String) -> AXUIElement? {
        if path == target.path { return element }
        for (index, child) in childElements(element).enumerated() {
            let childPath = "\(path)/\(index)"
            if target.path.hasPrefix(childPath), let found = findScrollTarget(child, path: childPath) { return found }
        }
        return nil
    }
    guard let targetElement = findScrollTarget(root, path: "root") else { exit(6) }
    let action = delta >= 0 ? "AXScrollUpByPage" : "AXScrollDownByPage"
    if AXUIElementPerformAction(targetElement, action as CFString) != .success { exit(7) }
case "click-button":
    guard CommandLine.arguments.count >= 4,
          let targetWidth = Double(CommandLine.arguments[2]),
          let targetHeight = Double(CommandLine.arguments[3]) else { exit(2) }
    app.activate(options: [.activateIgnoringOtherApps])
    let root = AXUIElementCreateApplication(app.processIdentifier)
    var records: [Record] = []
    var seen = Set<CFHashCode>()
    walk(root, path: "root", depth: 0, seen: &seen, records: &records)
    let candidates = records.filter { $0.role == kAXButtonRole as String && ($0.x ?? 10_000) < 400 }
    guard let targetRecord = candidates.min(by: {
        abs(($0.width ?? 0) - targetWidth) + abs(($0.height ?? 0) - targetHeight)
        < abs(($1.width ?? 0) - targetWidth) + abs(($1.height ?? 0) - targetHeight)
    }) else { exit(6) }
    func find(_ element: AXUIElement, path: String) -> AXUIElement? {
        if path == targetRecord.path { return element }
        for (index, child) in childElements(element).enumerated() {
            let childPath = "\(path)/\(index)"
            if targetRecord.path.hasPrefix(childPath), let found = find(child, path: childPath) { return found }
        }
        return nil
    }
    guard let targetElement = find(root, path: "root") else { exit(7) }
    let error = AXUIElementPerformAction(targetElement, kAXPressAction as CFString)
    if error != .success { exit(8) }
    let encoder = JSONEncoder()
    FileHandle.standardOutput.write(try encoder.encode(targetRecord))
    FileHandle.standardOutput.write(Data("\n".utf8))
default:
    fputs("unknown mode\n", stderr)
    exit(2)
}
