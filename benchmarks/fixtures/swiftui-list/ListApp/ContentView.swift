import SwiftUI

struct ContentView: View {
    @State private var model = ItemListModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                HStack {
                    TextField("New item", text: $model.draft)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityIdentifier("newItemField")
                    Button("Add") { model.add() }
                        .disabled(!model.canAdd)
                        .accessibilityIdentifier("addButton")
                }
                .padding(.horizontal)

                Text(model.countLabel)
                    .accessibilityIdentifier("countLabel")

                List {
                    ForEach(model.items) { item in
                        Text(item.title)
                    }
                    .onDelete { model.delete(at: $0) }
                }
                .accessibilityIdentifier("itemList")
            }
            .navigationTitle("List")
        }
    }
}
