import XCTest

final class ListAppUITests: XCTestCase {
    override func setUp() {
        continueAfterFailure = false
    }

    func testAddingAnItemShowsItAndTheCount() {
        let app = XCUIApplication()
        app.launch()
        let field = app.textFields["newItemField"]
        field.tap()
        field.typeText("Milk")
        app.buttons["addButton"].tap()
        XCTAssertTrue(app.staticTexts["Milk"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["countLabel"].label, "1 item")
    }

    func testAddButtonIsDisabledForBlankInput() {
        let app = XCUIApplication()
        app.launch()
        let field = app.textFields["newItemField"]
        field.tap()
        field.typeText("   ")
        XCTAssertFalse(app.buttons["addButton"].isEnabled)
    }

    func testEmptyStateIsShownWhenThereAreNoItems() {
        let app = XCUIApplication()
        app.launch()
        let empty = app.staticTexts["emptyState"]
        XCTAssertTrue(empty.waitForExistence(timeout: 5))
        XCTAssertEqual(empty.label, "No items yet")
    }
}
