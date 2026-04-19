library TestNotIn

define Test: not (1 in { 1, 2, 3, 4, 5 })
// Should we support not in:
// define TestNotIn: 1 not in { 1, 2, 3, 4, 5 }