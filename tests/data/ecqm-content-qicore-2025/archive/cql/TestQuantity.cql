library TestQuantity

// Expect true unless otherwise specified
define TestQuantityMillisecondEqualMs: 1 millisecond = 1 'ms'
define TestQuantityMillisecondEqualMilliseconds: 1 millisecond = 1 milliseconds
define TestQuantityMillisecondsEqualMs: 1 milliseconds = 1 'ms'
define TestQuantitySecondEqualS: 1 second = 1 's'
define TestQuantitySecondEqualSeconds: 1 second = 1 seconds
define TestQuantitySecondsEqualS: 1 seconds = 1 's'
define TestQuantityMinuteEqualMin: 1 minute = 1 'min'
define TestQuantityMinuteEqualMinutes: 1 minute = 1 minutes
define TestQuantityMinutesEqualMin: 1 minutes = 1 'min'
define TestQuantityHourEqualH: 1 hour = 1 'h'
define TestQuantityHourEqualHours: 1 hour = 1 hours
define TestQuantityHoursEqualH: 1 hours = 1 'h'
define TestQuantityDayEqualD: 1 day = 1 'd'
define TestQuantityDayEqualDays: 1 day = 1 days
define TestQuantityDaysEqualD: 1 days = 1 'd'
define TestQuantityWeekEqualWk: 1 week = 1 'wk'
define TestQuantityWeekEqualWeeks: 1 week = 1 weeks
define TestQuantityWeeksEqualWk: 1 weeks = 1 'wk'
define TestQuantityMonthEqualMo: 1 month = 1 'mo' // null (on the grounds that definite time and calendar units are not comparable)
define TestQuantityMonthNotEqualMo: 1 month != 1 'mo' // null (on the grounds that definite time and calendar units are not comparable)
define TestQuantityMonthEquivalentMo: 1 month ~ 1 'mo'
define TestQuantityMonthEqualMonths: 1 month = 1 months
define TestQuantityMonthsNotEqualMo: 1 months != 1 'mo' // null (on the grounds that definite time and calendar units are not comparable)
define TestQuantityMonthsEquivalentMo: 1 months ~ 1 'mo'
define TestQuantityYearEqualA: 1 year = 1 'a' // null (on the grounds that definite time and calendar units are not comparable)
define TestQuantityYearNotEqualA: 1 year != 1 'a' // null (on the grounds that definite time and calendar units are not comparable)
define TestQuantityYearEquivalentA: 1 year ~ 1 'a'
define TestQuantityYearsEqualYear: 1 years = 1 year
define TestQuantityYearsNotEqualA: 1 years != 1 'a'  // null (on the grounds that definite time and calendar units are not comparable)
define TestQuantityYearsEquivalentA: 1 years ~ 1 'a'

// Expect true if the engine supports unit conversion, null otherwise
define TestYearEqualMonths: 1 year = 12 months
define TestYearEquivalentMonths: 1 year ~ 12 months
define TestYearEquivalentDays: 1 year ~ 365 days
define TestMonthEquivalentDays: 1 month ~ 30 days
define TestWeekEqualDays: 1 week = 7 days
define TestDayEqualHours: 1 day = 24 hours
define TestHourEqualMinutes: 1 hour = 60 minutes
define TestMinuteEqualSeconds: 1 minute = 60 seconds
define TestSecondEqualMilliseconds: 1 second = 1000 milliseconds
