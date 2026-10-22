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
    @Binding var following: Bool
    @Binding var interacting: Bool
    let bottom: CGFloat
    let height: CGFloat
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.onScrollPhaseChange { _, phase in
                switch phase {
                case .tracking, .interacting, .decelerating: interacting = true; following = false
                case .idle: interacting = false; following = bottom <= height + 80
                default: break
                }
            }
        } else {
            content.simultaneousGesture(DragGesture().onChanged { _ in interacting = true; following = false }.onEnded { _ in interacting = false; following = bottom <= height + 80 })
        }
    }
}
