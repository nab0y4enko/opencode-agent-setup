import SwiftUI

struct Item: Identifiable, Equatable {
    let id = UUID()
    let title: String
}

@Observable
final class ItemListModel {
    private(set) var items: [Item] = []
    var draft: String = ""
    private(set) var countLabel: String = ItemListModel.label(for: 0)

    var canAdd: Bool {
        !draft.isEmpty
    }

    func add() {
        guard canAdd else { return }
        items.append(Item(title: draft))
        draft = ""
        countLabel = Self.label(for: items.count)
    }

    func delete(at offsets: IndexSet) {
        items.remove(atOffsets: offsets)
    }

    static func label(for count: Int) -> String {
        count == 1 ? "1 item" : "\(count) items"
    }
}
