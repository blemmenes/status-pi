// Prints "1" when any process is capturing audio input and "0" when none is,
// once at startup and then on every change. Output-only playback never counts,
// even on devices that have both input and output (USB interfaces, headsets).
// Requires macOS 14.4+ (CoreAudio process objects). Exits when stdin closes.
//
// Polls: CoreAudio does not deliver change notifications for a process's
// IsRunningInput (observed on macOS 26.6), only reads.
//
// Build: swiftc -O -o hammerspoon/micwatch hammerspoon/micwatch.swift

import CoreAudio
import Foundation

setvbuf(stdout, nil, _IOLBF, 0)

let queue = DispatchQueue(label: "micwatch")
let system = AudioObjectID(kAudioObjectSystemObject)

func globalAddress(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
        mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
}

var processListAddress = globalAddress(kAudioHardwarePropertyProcessObjectList)
var runningInputAddress = globalAddress(kAudioProcessPropertyIsRunningInput)

func processObjects() -> [AudioObjectID] {
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(system, &processListAddress, 0, nil, &size) == noErr else { return [] }
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(system, &processListAddress, 0, nil, &size, &ids) == noErr else { return [] }
    return ids
}

func isRunningInput(_ process: AudioObjectID) -> Bool {
    var value: UInt32 = 0
    var size = UInt32(MemoryLayout<UInt32>.size)
    return AudioObjectGetPropertyData(process, &runningInputAddress, 0, nil, &size, &value) == noErr && value != 0
}

var lastReported: Bool?

func poll() {
    let active = processObjects().contains(where: isRunningInput)
    if active != lastReported {
        lastReported = active
        print(active ? "1" : "0")
    }
}

guard AudioObjectHasProperty(system, &processListAddress) else {
    FileHandle.standardError.write("micwatch: CoreAudio process list unavailable (needs macOS 14.4+)\n".data(using: .utf8)!)
    exit(1)
}

let stdinSource = DispatchSource.makeReadSource(fileDescriptor: STDIN_FILENO, queue: queue)
stdinSource.setEventHandler {
    var buffer = [UInt8](repeating: 0, count: 64)
    if read(STDIN_FILENO, &buffer, buffer.count) <= 0 { exit(0) }
}
stdinSource.resume()

let timer = DispatchSource.makeTimerSource(queue: queue)
timer.schedule(deadline: .now(), repeating: .seconds(1), leeway: .milliseconds(200))
timer.setEventHandler(handler: poll)
timer.resume()
dispatchMain()
