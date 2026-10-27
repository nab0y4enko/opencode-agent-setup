import XCTest
@testable import ListApp

final class ItemListModelTests: XCTestCase {
    func testStartsEmpty() {
        let model = ItemListModel()
        XCTAssertTrue(model.items.isEmpty)
        XCTAssertEqual(model.countLabel, "0 items")
    }

    func testCannotAddEmptyText() {
        let model = ItemListModel()
        XCTAssertFalse(model.canAdd)
    }

    func testCannotAddWhitespaceOnlyText() {
        let model = ItemListModel()
        model.draft = "   \n "
        XCTAssertFalse(model.canAdd)
    }

    func testAddIsIgnoredWhenNotAllowed() {
        let model = ItemListModel()
        model.add()
        XCTAssertTrue(model.items.isEmpty)
    }

    func testAddTrimsTheTitle() {
        let model = ItemListModel()
        model.draft = "  Milk  "
        model.add()
        XCTAssertEqual(model.items.map(\.title), ["Milk"])
    }

    func testAddClearsTheDraft() {
        let model = ItemListModel()
        model.draft = "Milk"
        model.add()
        XCTAssertEqual(model.draft, "")
    }

    func testCountLabelIsSingularForOneItem() {
        let model = ItemListModel()
        model.draft = "Milk"
        model.add()
        XCTAssertEqual(model.countLabel, "1 item")
    }

    func testCountLabelIsPluralForTwoItems() {
        let model = ItemListModel()
        for title in ["Milk", "Eggs"] {
            model.draft = title
            model.add()
        }
        XCTAssertEqual(model.countLabel, "2 items")
    }

    func testDeleteUpdatesTheCountLabel() {
        let model = ItemListModel()
        for title in ["Milk", "Eggs"] {
            model.draft = title
            model.add()
        }
        model.delete(at: IndexSet(integer: 0))
        XCTAssertEqual(model.items.map(\.title), ["Eggs"])
        XCTAssertEqual(model.countLabel, "1 item")
    }
}
