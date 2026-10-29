import Foundation

/// Following is user intent, not a guess from a lazy stack's last measured frame.
/// Only a real drag pauses it; only an explicit jump (or initial open) resumes it.
struct ChatScrollState {
    private(set) var following = true
    private(set) var interacting = false
    private(set) var visibleID: String?
    private var userGesture = false

    // A top-anchored read position must never fight bottom-follow scroll commands.
    var positionID: String? { following ? nil : visibleID }
    var shouldFollow: Bool { following && !interacting }

    mutating func tracking() {
        userGesture = true
        interacting = true
    }
    mutating func dragged() {
        if following { visibleID = nil }
        userGesture = true
        interacting = true
        following = false
    }
    mutating func decelerating() {
        // Ignore residual inertia from the gesture superseded by "Latest".
        if userGesture { interacting = true }
    }
    mutating func idle() {
        interacting = false
        userGesture = false
        // Geometry/idle must not reverse explicit following or reading intent.
    }
    mutating func record(_ id: String?) {
        if !following { visibleID = id }
    }
    mutating func restore(_ id: String) {
        following = false; interacting = false; userGesture = false; visibleID = id
    }
    mutating func latest() {
        following = true; interacting = false; userGesture = false; visibleID = nil
    }
}
