# ListApp

A one-screen SwiftUI shopping list for iPhone.

## Behavior

- The text field (`newItemField`) holds the draft item title.
- The Add button (`addButton`) is enabled only when the draft contains a non-whitespace character.
  Adding stores the title with leading and trailing whitespace removed, then clears the field.
- The count label (`countLabel`) always shows the current number of items: `0 items`, `1 item`,
  `2 items`, and so on. It is correct after every add and every delete.
- When the list has no items, the screen shows the text `No items yet` (`emptyState`) instead of the
  empty list.
- Swiping an item deletes it.

## Checks

Run every unit and UI test on a named iOS simulator from the repository root:

    ./check.sh <simulator-name>

It prints `TESTS total=… passed=… failed=… skipped=…`, then one `FAILED <test>` line per failure,
and exits nonzero unless every test passed.
