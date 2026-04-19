library TestListEmpty

define EmptyList: { }
define EmptyListIsNull: EmptyList is null
define EmptyListEqualEmptyList: EmptyList = EmptyList
define TestDateNotEqual: @1974-12-25 != @1974-12-25T12:34:00
define TestDateEqual: @1974-12-25 = @1974-12-25T12:34:00
define TestDateToDateTime: ToDateTime(@1974-12-25)
define TestEmptyListIsNull: { } is null
define ExistsNull: exists null