import SwiftUI

struct ChatBottomPreference: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}
struct ChatHeightPreference: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}
struct ChatScrollInteraction: ViewModifier {
    @Binding var state: ChatScrollState
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.onScrollPhaseChange { _, phase in
                switch phase {
                case .tracking: state.tracking()
                case .interacting: state.dragged()
                case .decelerating: state.decelerating()
                case .idle: state.idle()
                default: break
                }
            }
        } else {
            content.simultaneousGesture(DragGesture(minimumDistance: 8).onChanged { _ in state.dragged() }.onEnded { _ in state.idle() })
        }
    }
}
