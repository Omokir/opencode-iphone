import Foundation

@main struct ChatScrollTests {
    static func main() {
        var state = ChatScrollState()
        precondition(state.shouldFollow && state.positionID == nil)
        state.record("msg_top")
        precondition(state.positionID == nil, "Visible top must not anchor streaming follow")
        state.tracking()
        precondition(state.following && !state.shouldFollow, "A touch pauses scroll without switching intent")
        state.dragged()
        state.record("msg_old")
        precondition(!state.following && state.positionID == "msg_old")
        state.decelerating(); state.idle()
        precondition(!state.following, "Idle and stale bottom geometry cannot resume follow")
        state.latest()
        precondition(state.shouldFollow && state.visibleID == nil && state.positionID == nil)
        state.decelerating()
        precondition(state.shouldFollow, "Residual inertia cannot undo Latest")
        state.idle()
        precondition(state.shouldFollow, "Streaming layout/idle cannot undo explicit Latest")
        state.tracking(); state.dragged(); state.idle()
        precondition(!state.shouldFollow, "A new manual drag pauses follow again")
        state.restore("msg_saved")
        precondition(!state.following && state.positionID == "msg_saved")
        state.idle()
        precondition(state.positionID == "msg_saved", "Opening history preserves saved reading position")
        state.latest(); state.tracking(); state.idle()
        precondition(state.shouldFollow, "Touch without dragging resumes prior follow intent")
        print("PASS: latest, drag, inertia, saved position and top-anchor ownership")
    }
}
