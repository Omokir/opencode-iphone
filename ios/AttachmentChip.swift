import SwiftUI
import ImageIO

struct AttachmentChip: View {
    let file: PendingFile
    let disabled: Bool
    let preview: () -> Void
    let remove: () -> Void
    @State private var thumbnail: UIImage?
    var body: some View {
        HStack(spacing: 6) {
            Button(action: preview) {
                HStack(spacing: 6) {
                    if let thumbnail { Image(uiImage: thumbnail).resizable().scaledToFill().frame(width: 32, height: 32).clipShape(RoundedRectangle(cornerRadius: 6)) }
                    else { Image(systemName: file.category == "image" ? "photo" : "doc") }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(file.name).lineLimit(1).frame(maxWidth: 190, alignment: .leading)
                        Text(ByteCountFormatter.string(fromByteCount: Int64(file.data.count), countStyle: .file)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }.accessibilityLabel("Prévia de \(file.name)")
            Button(action: remove) { Image(systemName: "xmark.circle.fill") }
                .accessibilityLabel("Remover \(file.name)").disabled(disabled)
        }.font(.caption).padding(10).background(Style.paper, in: RoundedRectangle(cornerRadius: 12))
            .task(id: file.id) {
                guard file.category == "image", let source = CGImageSourceCreateWithData(file.data as CFData, nil),
                      let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 96, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return }
                thumbnail = UIImage(cgImage: image)
            }
    }
}
